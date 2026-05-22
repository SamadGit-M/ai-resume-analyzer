# Asks Gemini to read a resume (or a JD) and give back a strict JSON object
# with the bits we care about. The schemas line up with what the chunker
# expects so we can go straight from extraction to chunking.
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from typing import Any

from ..config import settings
from .gemini_client import get_genai, call_with_retry

logger = logging.getLogger(__name__)

# Cache of past LLM extraction results, keyed by sha256(model + kind + text).
# Re-uploading the same resume or re-submitting the same JD costs zero LLM
# calls after the first time.
_EXTRACT_CACHE_DIR = os.path.join("./data", "extract_cache")
os.makedirs(_EXTRACT_CACHE_DIR, exist_ok=True)


def _cache_path(text: str, kind: str) -> str:
    key = f"{settings.GEMINI_LLM_MODEL}|{kind}|{text}".encode("utf-8")
    h = hashlib.sha256(key).hexdigest()
    return os.path.join(_EXTRACT_CACHE_DIR, f"{kind}_{h}.json")


def _load_cached(text: str, kind: str) -> dict[str, Any] | None:
    p = _cache_path(text, kind)
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save_cached(text: str, kind: str, data: dict[str, Any]) -> None:
    try:
        with open(_cache_path(text, kind), "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception as e:
        logger.debug("Could not write extract cache: %s", e)


RESUME_PROMPT = """You are a precise resume parser. Extract the following fields from the resume text and return STRICT JSON only — no prose, no markdown fences.

Schema:
{
  "name": string | null,
  "email": string | null,
  "phone": string | null,
  "location": string | null,
  "linkedin": string | null,
  "github": string | null,
  "summary": string | null,
  "skills": string[],
  "experience": [
    { "role": string, "company": string, "duration": string, "description": string }
  ],
  "education": [
    { "degree": string, "institution": string, "year": string }
  ],
  "projects": [
    { "title": string, "description": string, "tech": string[] }
  ],
  "certifications": string[]
}

Rules:
- If a field is missing, use null or an empty array.
- "skills" must be a flat array of individual skill tokens (e.g. "Python", "Kubernetes").
- "description" inside experience should be a single string, summarising bullet points.
- Do NOT invent information that is not in the resume.

Resume text:
---
{TEXT}
---
Return only valid JSON.
"""


JD_PROMPT = """You are a precise job-description parser. Extract the following fields from the JD text and return STRICT JSON only — no prose, no markdown fences.

Schema:
{
  "title": string | null,
  "required_skills": string[],
  "nice_to_have_skills": string[],
  "responsibilities": string[],
  "requirements": string[],
  "education_requirements": string[],
  "min_years_experience": number | null
}

Rules:
- Each list item should be a single concise phrase.
- Skills must be individual tokens (e.g. "Python", "AWS"), not full sentences.
- Do NOT invent requirements not present in the JD.

Job description:
---
{TEXT}
---
Return only valid JSON.
"""


def extract_resume(text: str) -> dict[str, Any]:
    cached = _load_cached(text, "resume")
    if cached is not None:
        return cached
    fallback = _empty_resume_schema()
    result = _extract(text, RESUME_PROMPT, fallback=fallback)
    if result != fallback:
        _save_cached(text, "resume", result)
    return result


def extract_jd(text: str) -> dict[str, Any]:
    cached = _load_cached(text, "jd")
    if cached is not None:
        return cached
    fallback = _empty_jd_schema()
    result = _extract(text, JD_PROMPT, fallback=fallback)
    if result != fallback:
        _save_cached(text, "jd", result)
    return result


def _extract(text: str, prompt_template: str, fallback: dict[str, Any]) -> dict[str, Any]:
    try:
        genai = get_genai()
        model = genai.GenerativeModel(
            model_name=settings.GEMINI_LLM_MODEL,
            generation_config={
                "response_mime_type": "application/json",
                "temperature": 0.1,
                # Resumes with lots of bullets can produce >2k tokens of JSON.
                # Default cap is low enough that the response sometimes gets
                # truncated mid-object, which is what causes "Could not parse
                # LLM JSON" warnings.
                "max_output_tokens": 8192,
            },
        )
        prompt = prompt_template.replace("{TEXT}", text[:30000])
        resp = call_with_retry(lambda: model.generate_content(prompt))
        raw = (resp.text or "").strip()
        return _safe_json_loads(raw, fallback)
    except Exception as e:
        logger.exception("LLM extraction failed: %s", e)
        return fallback


def _safe_json_loads(raw: str, fallback: dict[str, Any]) -> dict[str, Any]:
    if not raw:
        return fallback
    # Strip code fences just in case the model wraps the JSON in ```json ... ```
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw.strip())
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Sometimes the model leaks a sentence before the JSON. Grab the
        # first {...} block and try again.
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    logger.warning(
        "Could not parse LLM JSON, using fallback. First 400 chars of response: %r",
        raw[:400],
    )
    return fallback


def _empty_resume_schema() -> dict[str, Any]:
    return {
        "name": None, "email": None, "phone": None, "location": None,
        "linkedin": None, "github": None, "summary": None,
        "skills": [], "experience": [], "education": [],
        "projects": [], "certifications": [],
    }


def _empty_jd_schema() -> dict[str, Any]:
    return {
        "title": None,
        "required_skills": [], "nice_to_have_skills": [],
        "responsibilities": [], "requirements": [],
        "education_requirements": [], "min_years_experience": None,
    }
