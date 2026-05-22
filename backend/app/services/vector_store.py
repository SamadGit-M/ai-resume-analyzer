# Thin wrapper around ChromaDB. We pass embeddings in ourselves (computed by
# the embeddings module) instead of letting Chroma do it, so Chroma never
# needs to know about Gemini. Section metadata is stored alongside each
# chunk so the feedback step can filter on it.
from __future__ import annotations

import logging
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from ..config import settings
from .chunker import Chunk
from .embeddings import embed_texts

logger = logging.getLogger(__name__)

_client = None
_collection = None


def _get_collection():
    global _client, _collection
    if _collection is not None:
        return _collection
    _client = chromadb.PersistentClient(
        path=settings.CHROMA_DIR,
        settings=ChromaSettings(anonymized_telemetry=False, allow_reset=True),
    )
    _collection = _client.get_or_create_collection(
        name="resume_chunks",
        metadata={"hnsw:space": "cosine"},
    )
    return _collection


def index_resume_chunks(resume_id: int, chunks: list[Chunk]) -> None:
    if not chunks:
        return
    col = _get_collection()
    # Drop any old chunks for this resume so we don't end up with duplicates
    # after a re-upload.
    try:
        col.delete(where={"resume_id": resume_id})
    except Exception:
        pass

    ids = [f"r{resume_id}_c{i}" for i in range(len(chunks))]
    texts = [c.text for c in chunks]
    metadatas = [
        {"resume_id": resume_id, "section": c.section, **{k: _coerce(v) for k, v in c.metadata.items()}}
        for c in chunks
    ]
    vectors = embed_texts(texts)
    col.add(
        ids=ids,
        documents=texts,
        metadatas=metadatas,
        embeddings=[v.tolist() for v in vectors],
    )


def query_resume(resume_id: int, query_text: str, k: int = 4, section: str | None = None) -> list[dict[str, Any]]:
    col = _get_collection()
    where: dict[str, Any] = {"resume_id": resume_id}
    if section:
        where = {"$and": [{"resume_id": resume_id}, {"section": section}]}
    q_vec = embed_texts([query_text])[0]
    try:
        res = col.query(
            query_embeddings=[q_vec.tolist()],
            n_results=k,
            where=where,
        )
    except Exception as e:
        logger.warning("Chroma query failed: %s", e)
        return []
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]
    return [
        {"text": d, "metadata": m, "distance": dist}
        for d, m, dist in zip(docs, metas, dists)
    ]


def _coerce(v: Any) -> Any:
    # Chroma metadata only accepts primitives. Flatten anything else to a string.
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v if v is not None else ""
    if isinstance(v, list):
        return ", ".join(str(x) for x in v)
    return str(v)
