# One spot that owns the genai.configure() call, plus a retry helper for
# the 429s that hit pretty often on the free tier.
import logging
import re
import time
from typing import Callable, TypeVar

import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted

from ..config import settings

logger = logging.getLogger(__name__)

_configured = False

T = TypeVar("T")


def get_genai():
    global _configured
    if not _configured:
        if not settings.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is not configured.")
        genai.configure(api_key=settings.GEMINI_API_KEY)
        _configured = True
    return genai


def call_with_retry(fn: Callable[[], T], *, max_attempts: int = 3) -> T:
    # Retries on 429 ResourceExhausted. If the API tells us how long to wait
    # we use that, otherwise exponential backoff capped at 30s.
    attempt = 0
    while True:
        attempt += 1
        try:
            return fn()
        except ResourceExhausted as e:
            if attempt >= max_attempts:
                raise
            delay = _extract_retry_delay(str(e))
            if delay is None:
                delay = min(2 ** attempt, 30)
            logger.warning("Gemini 429 — retrying in %ss (attempt %s/%s)", delay, attempt, max_attempts)
            time.sleep(delay)


def _extract_retry_delay(text: str) -> float | None:
    m = re.search(r"retry in ([\d.]+)s", text)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    m = re.search(r"seconds:\s*(\d+)", text)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return None
