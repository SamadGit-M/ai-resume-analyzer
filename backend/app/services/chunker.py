# Document structure based chunking for resumes.
#
# Each top-level resume section (skills / experience / education / etc.)
# becomes a chunk. Inside experience, education and projects, each individual
# entry is its own sub-chunk. The metadata on each chunk says which section
# it belongs to so the scorer and ChromaDB can filter on it.
#
# Preferred path is chunk_resume_from_structured() which works off the JSON
# the LLM extractor returns. chunk_resume_from_blocks() is the fallback when
# the LLM call fails or has no quota left.
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .parser import ParsedDocument, TextBlock


SECTION_KEYWORDS = {
    "summary": ["summary", "profile", "objective", "about"],
    "skills": ["skills", "technical skills", "core competencies", "technologies"],
    "experience": ["experience", "work experience", "employment", "professional experience", "work history"],
    "education": ["education", "academic background", "academics", "qualifications"],
    "projects": ["projects", "personal projects", "selected projects"],
    "certifications": ["certifications", "certificates", "licenses"],
    "contact": ["contact", "contact information"],
}

CANONICAL_SECTIONS = list(SECTION_KEYWORDS.keys())


@dataclass
class Chunk:
    text: str
    section: str  # canonical section name
    metadata: dict[str, Any] = field(default_factory=dict)


# --- preferred path: chunks from the LLM's structured output ---

def chunk_resume_from_structured(structured: dict[str, Any]) -> list[Chunk]:
    chunks: list[Chunk] = []

    contact_bits = []
    for k in ("name", "email", "phone", "location", "linkedin", "github"):
        v = structured.get(k)
        if v:
            contact_bits.append(f"{k}: {v}")
    if contact_bits:
        chunks.append(Chunk(text="; ".join(contact_bits), section="contact"))

    summary = structured.get("summary")
    if summary:
        chunks.append(Chunk(text=str(summary), section="summary"))

    skills = structured.get("skills") or []
    if skills:
        if isinstance(skills, list):
            text = "Skills: " + ", ".join(str(s) for s in skills)
        else:
            text = "Skills: " + str(skills)
        chunks.append(Chunk(text=text, section="skills", metadata={"skills_list": skills if isinstance(skills, list) else [skills]}))

    for exp in structured.get("experience", []) or []:
        role = exp.get("role") or exp.get("title") or ""
        company = exp.get("company") or ""
        duration = exp.get("duration") or exp.get("dates") or ""
        desc = exp.get("description") or ""
        if isinstance(desc, list):
            desc = " ".join(str(d) for d in desc)
        text = " ".join(p for p in [
            f"{role} at {company}".strip(" at"),
            f"({duration})" if duration else "",
            str(desc),
        ] if p).strip()
        if text:
            chunks.append(Chunk(
                text=text,
                section="experience",
                metadata={"role": role, "company": company, "duration": duration},
            ))

    for edu in structured.get("education", []) or []:
        degree = edu.get("degree") or ""
        inst = edu.get("institution") or edu.get("school") or ""
        year = edu.get("year") or edu.get("dates") or ""
        text = " ".join(p for p in [degree, inst, str(year)] if p).strip(", ").strip()
        if text:
            chunks.append(Chunk(text=text, section="education", metadata={"degree": degree, "institution": inst, "year": year}))

    for proj in structured.get("projects", []) or []:
        title = proj.get("title") or proj.get("name") or ""
        desc = proj.get("description") or ""
        if isinstance(desc, list):
            desc = " ".join(str(d) for d in desc)
        tech = proj.get("tech") or proj.get("technologies") or []
        if isinstance(tech, list):
            tech_str = ", ".join(str(t) for t in tech)
        else:
            tech_str = str(tech)
        text = " ".join(p for p in [title, str(desc), f"Tech: {tech_str}" if tech_str else ""] if p).strip()
        if text:
            chunks.append(Chunk(text=text, section="projects", metadata={"title": title, "tech": tech}))

    for cert in structured.get("certifications", []) or []:
        if isinstance(cert, dict):
            text = " ".join(str(v) for v in cert.values() if v)
        else:
            text = str(cert)
        if text:
            chunks.append(Chunk(text=text, section="certifications"))

    return chunks


# --- fallback path: heading-based heuristic ---

def chunk_resume_from_blocks(parsed: ParsedDocument) -> list[Chunk]:
    # Walk top to bottom, attach each line to the most recent heading.
    sections: dict[str, list[str]] = {}
    current_section = "summary"

    for block in parsed.blocks:
        canon = _detect_section(block.text, is_heading_hint=block.is_heading)
        if canon and (block.is_heading or _looks_like_pure_heading(block.text)):
            current_section = canon
            continue
        sections.setdefault(current_section, []).append(block.text)

    chunks: list[Chunk] = []
    for sec, lines in sections.items():
        if sec == "experience":
            for entry in _split_entries(lines):
                chunks.append(Chunk(text=entry, section="experience"))
        elif sec == "education":
            for entry in _split_entries(lines):
                chunks.append(Chunk(text=entry, section="education"))
        elif sec == "projects":
            for entry in _split_entries(lines):
                chunks.append(Chunk(text=entry, section="projects"))
        else:
            text = "\n".join(lines).strip()
            if text:
                chunks.append(Chunk(text=text, section=sec))
    return chunks


def _detect_section(text: str, is_heading_hint: bool = False) -> str | None:
    t = text.strip().lower().rstrip(":").strip()
    if len(t) > 50:
        return None
    # If the line looks like a heading by shape (short + mostly uppercase),
    # treat it as a heading even when the parser didn't flag it via font
    # size. This catches PDFs where pdfplumber's font metrics are noisy but
    # the section titles are still visually obvious like "TECHNICAL SKILLS"
    # or "KEY PROJECTS".
    looks_heading = is_heading_hint or _looks_like_pure_heading(text)
    for canon, kws in SECTION_KEYWORDS.items():
        for kw in kws:
            if t == kw or (looks_heading and kw in t):
                return canon
    return None


def _looks_like_pure_heading(text: str) -> bool:
    t = text.strip().rstrip(":").strip()
    if len(t) > 40:
        return False
    # short + mostly uppercase -> probably a heading
    letters = [c for c in t if c.isalpha()]
    if not letters:
        return False
    upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
    return upper_ratio > 0.7


def _split_entries(lines: list[str]) -> list[str]:
    # Try to detect where one entry ends and the next begins.
    # Blank line = new entry. A line starting with a capital letter that
    # also contains a year is usually a new "Role at Company (year-year)".
    entries: list[str] = []
    buf: list[str] = []
    for ln in lines:
        if not ln.strip():
            if buf:
                entries.append("\n".join(buf).strip())
                buf = []
            continue
        # A line that looks like a new entry header (Title Case + date-ish) starts a new entry
        if buf and re.search(r"(19|20)\d{2}", ln) and re.match(r"^[A-Z]", ln) and len(ln) < 120:
            entries.append("\n".join(buf).strip())
            buf = [ln]
            continue
        buf.append(ln)
    if buf:
        entries.append("\n".join(buf).strip())
    return [e for e in entries if e]


# --- JD chunking ---

def chunk_job_description(jd_text: str, structured: dict[str, Any] | None = None) -> list[Chunk]:
    # Use the extractor's structured output if we have it. Otherwise fall
    # back to splitting on bullets / numbered lines.
    chunks: list[Chunk] = []

    if structured:
        for req in structured.get("required_skills", []) or []:
            chunks.append(Chunk(text=str(req), section="skills", metadata={"jd_section": "required_skills"}))
        for req in structured.get("nice_to_have_skills", []) or []:
            chunks.append(Chunk(text=str(req), section="skills", metadata={"jd_section": "nice_to_have"}))
        for req in structured.get("responsibilities", []) or []:
            chunks.append(Chunk(text=str(req), section="experience", metadata={"jd_section": "responsibilities"}))
        for req in structured.get("requirements", []) or []:
            chunks.append(Chunk(text=str(req), section="experience", metadata={"jd_section": "requirements"}))
        for req in structured.get("education_requirements", []) or []:
            chunks.append(Chunk(text=str(req), section="education", metadata={"jd_section": "education"}))
        if chunks:
            return chunks

    bullet_re = re.compile(r"^\s*[-•*\d+\.\)]+\s*(.+)")
    for line in jd_text.splitlines():
        line = line.rstrip()
        if not line.strip():
            continue
        m = bullet_re.match(line)
        content = m.group(1) if m else line.strip()
        if len(content) < 4:
            continue
        # quick guess at which section this line is about
        low = content.lower()
        if any(k in low for k in ["degree", "bachelor", "master", "phd", "b.tech", "m.tech"]):
            sec = "education"
        elif any(k in low for k in ["year", "experience", "responsible", "develop", "build", "design", "lead"]):
            sec = "experience"
        else:
            sec = "skills"
        chunks.append(Chunk(text=content, section=sec, metadata={"jd_section": "raw"}))
    return chunks
