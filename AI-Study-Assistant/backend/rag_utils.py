import os
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import chromadb

from ai_utils import normalize_text
from ai_service import AIServiceError, embed_texts


def _persist_dir() -> str:
    backend_dir = Path(__file__).resolve().parent
    project_root = backend_dir.parent
    base = project_root / "database" / "chroma"
    base.mkdir(parents=True, exist_ok=True)
    return str(base)


@lru_cache(maxsize=1)
def _client():
    return chromadb.PersistentClient(path=_persist_dir())


@lru_cache(maxsize=1)
def _collection():
    # Single collection; filter by metadata (user_id, doc_id)
    return _client().get_or_create_collection(name="study_assistant_notes")


def _chunk_text(text: str, chunk_size: int = 900, overlap: int = 120) -> List[str]:
    """
    Simple chunker by characters. Keeps dependencies minimal.
    """
    text = normalize_text(text or "")
    if not text:
        return []
    chunks: List[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(n, start + chunk_size)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap
        if start < 0:
            start = 0
        if end == n:
            break
    return chunks


def store_document_embeddings(text: str, doc_id: int, user_id: int) -> Dict[str, int]:
    """
    Chunk notes and store embeddings in Chroma.
    Returns {"chunks": X, "stored": Y}.
    """
    chunks = _chunk_text(text)
    if not chunks:
        return {"chunks": 0, "stored": 0}

    col = _collection()

    # Avoid duplicates: if we already have chunks for this doc/user, skip.
    try:
        existing = col.get(where={"doc_id": int(doc_id), "user_id": int(user_id)}, limit=1)
        if existing and existing.get("ids"):
            return {"chunks": len(chunks), "stored": 0}
    except Exception:
        # If get() fails, just proceed to add (Chroma will overwrite by ids if same).
        pass

    ids = [f"u{user_id}_d{doc_id}_c{i}" for i in range(len(chunks))]
    metas = [{"user_id": int(user_id), "doc_id": int(doc_id), "chunk_index": i} for i in range(len(chunks))]

    # Embeddings are created via OpenAI (env key required)
    try:
        embs = embed_texts(chunks)
    except Exception as e:
        raise AIServiceError("Embedding generation failed. Check OPENAI_API_KEY.") from e

    col.add(ids=ids, documents=chunks, metadatas=metas, embeddings=embs)
    return {"chunks": len(chunks), "stored": len(chunks)}


def retrieve_relevant_chunks(
    query: str, user_id: int, doc_id: Optional[int] = None, k: int = 6
) -> List[str]:
    """
    Retrieve top-k relevant chunks from Chroma for a given user (and optionally note/doc).
    """
    q = normalize_text(query or "")
    if not q:
        return []

    where = {"user_id": int(user_id)}
    if doc_id is not None:
        where["doc_id"] = int(doc_id)

    col = _collection()
    try:
        q_emb = embed_texts([q])[0]
    except Exception as e:
        raise AIServiceError("Query embedding failed. Check OPENAI_API_KEY.") from e

    res = col.query(
        query_embeddings=[q_emb],
        n_results=int(k),
        where=where,
        include=["documents", "metadatas", "distances"],
    )
    docs = (res.get("documents") or [[]])[0]
    return [d for d in docs if d]

