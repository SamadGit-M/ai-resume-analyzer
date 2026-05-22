# Wrapper around Gemini embeddings with a SHA-256 disk cache so we don't
# burn API calls on the same text twice.
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading

import numpy as np

from ..config import settings
from .gemini_client import get_genai, call_with_retry

logger = logging.getLogger(__name__)

_CACHE_DIR = os.path.join("./data", "emb_cache")
os.makedirs(_CACHE_DIR, exist_ok=True)
_lock = threading.Lock()

# gemini-embedding-001 returns 3072-dim vectors. If you change the embedding
# model in .env, update this constant AND wipe data/chroma/ because Chroma
# locks the collection dim on first write.
EMBEDDING_DIM = 3072


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _cache_path(h: str) -> str:
    return os.path.join(_CACHE_DIR, f"{h}.json")


def embed_text(text: str) -> np.ndarray:
    return embed_texts([text])[0]


def embed_texts(texts: list[str]) -> list[np.ndarray]:
    # Looks up each text in the disk cache first, only calls Gemini for the
    # ones we haven't seen.
    results: list[np.ndarray | None] = [None] * len(texts)
    to_compute: list[tuple[int, str, str]] = []  # (idx, text, hash)

    for i, t in enumerate(texts):
        h = _hash(t)
        cached = _load_cache(h)
        if cached is not None:
            results[i] = cached
        else:
            to_compute.append((i, t, h))

    if to_compute:
        try:
            vectors = _call_gemini([t for _, t, _ in to_compute])
        except Exception as e:
            logger.exception("Gemini embedding failed, falling back to zero vectors: %s", e)
            vectors = [np.zeros(EMBEDDING_DIM, dtype=np.float32) for _ in to_compute]

        for (idx, _t, h), vec in zip(to_compute, vectors):
            results[idx] = vec
            _save_cache(h, vec)

    return [r if r is not None else np.zeros(EMBEDDING_DIM, dtype=np.float32) for r in results]


def _model_name() -> str:
    name = settings.GEMINI_EMBEDDING_MODEL.strip()
    if name.startswith("models/") or name.startswith("tunedModels/"):
        return name
    return f"models/{name}"


def _call_gemini(texts: list[str]) -> list[np.ndarray]:
    genai = get_genai()
    model = _model_name()
    payloads = [t[:8000] for t in texts]

    # Try the batch endpoint first - one HTTP call instead of N. If the SDK
    # version we're on doesn't accept a list (older SDKs return a single
    # embedding for a list), fall back to per-text calls.
    try:
        resp = call_with_retry(lambda: genai.embed_content(
            model=model,
            content=payloads,
            task_type="retrieval_document",
        ))
        embeddings = resp.get("embedding") if isinstance(resp, dict) else getattr(resp, "embedding", None)
        if embeddings and isinstance(embeddings, list) and len(embeddings) == len(payloads) and isinstance(embeddings[0], list):
            return [np.asarray(v, dtype=np.float32) for v in embeddings]
    except Exception as e:
        logger.debug("Batch embed failed (%s), falling back to per-text calls.", e)

    out: list[np.ndarray] = []
    for payload in payloads:
        resp = call_with_retry(lambda p=payload: genai.embed_content(
            model=model,
            content=p,
            task_type="retrieval_document",
        ))
        vec = resp.get("embedding") if isinstance(resp, dict) else getattr(resp, "embedding", None)
        if vec is None:
            raise RuntimeError(f"Empty embedding response: {resp}")
        out.append(np.asarray(vec, dtype=np.float32))
    return out


def _load_cache(h: str) -> np.ndarray | None:
    path = _cache_path(h)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            data = json.load(f)
        return np.asarray(data, dtype=np.float32)
    except Exception:
        return None


def _save_cache(h: str, vec: np.ndarray) -> None:
    path = _cache_path(h)
    try:
        with _lock:
            with open(path, "w") as f:
                json.dump(vec.tolist(), f)
    except Exception as e:
        logger.warning("Failed to write embedding cache: %s", e)


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    if a.size == 0 or b.size == 0:
        return 0.0
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))
