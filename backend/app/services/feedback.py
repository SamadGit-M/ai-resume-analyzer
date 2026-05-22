# Builds the strengths/improvements lists for one resume vs one JD.
#
# RAG step: for each of the top JD requirements, pull the most relevant
# resume chunks out of ChromaDB and feed those into a Gemini prompt. That
# keeps the prompt small and lets the model ground its feedback in actual
# resume content instead of hallucinating.
#
# If Gemini errors out (quota, network, malformed JSON) we fall back to a
# deterministic template so the endpoint still returns something useful.
from __future__ import annotations

import json
import logging
import re
from typing import Any

from ..config import settings
from .gemini_client import get_genai, call_with_retry
from .vector_store import query_resume

logger = logging.getLogger(__name__)

FEEDBACK_PROMPT = """You are an expert technical recruiter providing feedback on a candidate.
Given the job requirements and retrieved snippets from the candidate's resume, generate STRICT JSON only.

Schema:
{
  "strengths": string[],   // 3-5 concrete strengths backed by the resume
  "improvements": string[] // 3-5 actionable, specific suggestions
}

Rules:
- Reference concrete items the candidate has (or is missing) — do NOT be generic.
- If a required skill is missing from the snippets, name it directly in improvements.
- Keep each item under 25 words.

Job Title: {JOB_TITLE}

Required skills: {REQUIRED_SKILLS}
Nice-to-have skills: {NICE_SKILLS}
Key responsibilities: {RESPONSIBILITIES}

Retrieved candidate snippets:
{SNIPPETS}

Matched skills: {MATCHED}
Missing skills: {MISSING}

Return only valid JSON.
"""


def generate_feedback(
    resume_id: int,
    job_structured: dict[str, Any],
    matched_skills: list[str],
    missing_skills: list[str],
) -> dict[str, list[str]]:
    job_title = job_structured.get("title") or "the role"
    required = job_structured.get("required_skills") or []
    nice = job_structured.get("nice_to_have_skills") or []
    resp = job_structured.get("responsibilities") or []

    # Pick the queries we'll run against ChromaDB. Cap them so we don't
    # blow up the prompt size.
    queries = []
    for s in required[:6]:
        queries.append(str(s))
    for r in resp[:4]:
        queries.append(str(r))

    snippet_lines: list[str] = []
    seen_texts: set[str] = set()
    for q in queries:
        hits = query_resume(resume_id, q, k=2)
        for h in hits:
            t = h["text"].strip()
            if t and t not in seen_texts:
                seen_texts.add(t)
                meta = h.get("metadata") or {}
                section = meta.get("section", "?")
                snippet_lines.append(f"- [{section}] {t}")
        if len(snippet_lines) >= 15:
            break

    snippets_block = "\n".join(snippet_lines) if snippet_lines else "(no snippets retrieved)"

    prompt = (
        FEEDBACK_PROMPT
        .replace("{JOB_TITLE}", str(job_title))
        .replace("{REQUIRED_SKILLS}", ", ".join(map(str, required)) or "(none listed)")
        .replace("{NICE_SKILLS}", ", ".join(map(str, nice)) or "(none listed)")
        .replace("{RESPONSIBILITIES}", "; ".join(map(str, resp)) or "(none listed)")
        .replace("{SNIPPETS}", snippets_block)
        .replace("{MATCHED}", ", ".join(matched_skills) or "(none)")
        .replace("{MISSING}", ", ".join(missing_skills) or "(none)")
    )

    try:
        genai = get_genai()
        model = genai.GenerativeModel(
            model_name=settings.GEMINI_LLM_MODEL,
            generation_config={"response_mime_type": "application/json", "temperature": 0.4},
        )
        resp_obj = call_with_retry(lambda: model.generate_content(prompt))
        raw = (resp_obj.text or "").strip()
        return _parse_feedback(raw, matched_skills, missing_skills)
    except Exception as e:
        logger.exception("Feedback generation failed: %s", e)
        return _fallback_feedback(matched_skills, missing_skills)


def _parse_feedback(raw: str, matched: list[str], missing: list[str]) -> dict[str, list[str]]:
    if not raw:
        return _fallback_feedback(matched, missing)
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw.strip())
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return _fallback_feedback(matched, missing)
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return _fallback_feedback(matched, missing)
    strengths = data.get("strengths") or []
    improvements = data.get("improvements") or []
    return {
        "strengths": [str(x) for x in strengths][:6],
        "improvements": [str(x) for x in improvements][:6],
    }


def _fallback_feedback(matched: list[str], missing: list[str]) -> dict[str, list[str]]:
    strengths = []
    if matched:
        strengths.append(f"Demonstrates required skills: {', '.join(matched[:6])}.")
    else:
        strengths.append("Resume parsed successfully; review experience section for relevant projects.")

    improvements = []
    if missing:
        improvements.append(f"Add or highlight experience with: {', '.join(missing[:6])}.")
    improvements.append("Quantify achievements with numbers (e.g. impact, scale, performance).")
    improvements.append("Tailor the summary section to the specific job title.")

    return {"strengths": strengths, "improvements": improvements}
