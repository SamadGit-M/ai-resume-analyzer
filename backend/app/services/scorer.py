# Per-section similarity scoring.
#
# All scores are 0-100.
#
#   skills      = 0.6 * keyword_overlap%  +  0.4 * mean_section_cosine * 100
#   experience  = mean( best resume-cosine for each JD requirement chunk ) * 100
#   education   = same idea for education chunks
#   total       = 0.50*skills + 0.35*experience + 0.15*education
#
# Skills gets the keyword-overlap bias because exact skill names matter more
# than semantic similarity for the skills section (e.g. "Python" vs "Java"
# would score high on cosine but should fail the skill match).
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np

from .chunker import Chunk
from .embeddings import cosine, embed_texts

logger = logging.getLogger(__name__)

WEIGHTS = {"skills": 0.50, "experience": 0.35, "education": 0.15}


@dataclass
class ScoreBreakdown:
    total_score: float
    skills_score: float
    experience_score: float
    education_score: float
    matched_skills: list[str]
    missing_skills: list[str]


def score_resume(
    resume_structured: dict[str, Any],
    resume_chunks: list[Chunk],
    jd_structured: dict[str, Any],
    jd_chunks: list[Chunk],
) -> ScoreBreakdown:
    # ---- Skills ----
    resume_skills_raw = resume_structured.get("skills") or []
    jd_skills_raw = (jd_structured.get("required_skills") or []) + (jd_structured.get("nice_to_have_skills") or [])
    matched, missing, overlap_pct = _keyword_overlap(jd_skills_raw, resume_skills_raw)

    skill_cosine = _section_cosine(jd_chunks, resume_chunks, section="skills")
    skills_score = round(0.6 * overlap_pct + 0.4 * skill_cosine * 100, 2)

    # ---- Experience ----
    experience_score = round(_section_cosine(jd_chunks, resume_chunks, section="experience") * 100, 2)

    # ---- Education ----
    education_score = round(_section_cosine(jd_chunks, resume_chunks, section="education") * 100, 2)

    total = round(
        WEIGHTS["skills"] * skills_score
        + WEIGHTS["experience"] * experience_score
        + WEIGHTS["education"] * education_score,
        2,
    )

    return ScoreBreakdown(
        total_score=total,
        skills_score=skills_score,
        experience_score=experience_score,
        education_score=education_score,
        matched_skills=matched,
        missing_skills=missing,
    )


def _keyword_overlap(jd_skills: list[str], resume_skills: list[str]) -> tuple[list[str], list[str], float]:
    jd_norm = {_norm(s): s for s in jd_skills if str(s).strip()}
    resume_norm = {_norm(s) for s in resume_skills if str(s).strip()}
    if not jd_norm:
        return [], [], 0.0
    matched = [orig for k, orig in jd_norm.items() if k in resume_norm or any(k in r or r in k for r in resume_norm)]
    missing = [orig for k, orig in jd_norm.items() if orig not in matched]
    pct = 100.0 * len(matched) / len(jd_norm)
    return matched, missing, round(pct, 2)


def _norm(s: str) -> str:
    return "".join(ch.lower() for ch in str(s).strip() if ch.isalnum() or ch == "+")


def _section_cosine(jd_chunks: list[Chunk], resume_chunks: list[Chunk], section: str) -> float:
    # For each JD chunk in this section, find the best-matching resume
    # chunk in the same section. Return the mean of those best-matches.
    jd_section = [c for c in jd_chunks if c.section == section]
    if not jd_section:
        return 0.0

    res_section = [c for c in resume_chunks if c.section == section]
    # Graceful fallback: if structured extraction failed and nothing got
    # tagged as this section, match against ALL resume chunks instead of
    # returning 0. Better than nothing, and the heuristic chunker often
    # dumps everything into a single "summary" bucket when section headings
    # are missing from the PDF.
    if not res_section:
        res_section = resume_chunks
    if not res_section:
        return 0.0

    all_texts = [c.text for c in jd_section] + [c.text for c in res_section]
    vectors = embed_texts(all_texts)
    jd_vecs = vectors[: len(jd_section)]
    res_vecs = vectors[len(jd_section):]

    bests = []
    for j in jd_vecs:
        sims = [cosine(j, r) for r in res_vecs]
        bests.append(max(sims) if sims else 0.0)
    return float(np.mean(bests)) if bests else 0.0
