"""
RAG engine for Verdant community bot.

Loads the knowledge base, embeds it with sentence-transformers,
stores vectors in a FAISS index, and exposes `retrieve()` for
semantic search.
"""
import json
import os
from pathlib import Path
from typing import List, Dict, Any

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

# ---------- Config ----------
KB_PATH = Path(__file__).resolve().parent.parent / "data" / "knowledge_base.json"
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBED_DIM = 384  # dimension for all-MiniLM-L6-v2

# ---------- Module state (loaded once) ----------
_model: SentenceTransformer | None = None
_index: faiss.IndexFlatL2 | None = None
_kb: List[Dict[str, Any]] = []


def _load_kb() -> List[Dict[str, Any]]:
    """Load and validate the knowledge base JSON."""
    if not KB_PATH.exists():
        raise FileNotFoundError(f"Knowledge base not found at {KB_PATH}")
    with open(KB_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list) or not data:
        raise ValueError("Knowledge base must be a non-empty JSON array.")
    required = {"id", "category", "question", "answer"}
    for i, entry in enumerate(data):
        missing = required - entry.keys()
        if missing:
            raise ValueError(f"KB entry {i} missing keys: {missing}")
    return data


def _get_model() -> SentenceTransformer:
    """Lazy-load the embedding model (downloads on first run)."""
    global _model
    if _model is None:
        print(f"[rag] Loading embedding model: {MODEL_NAME}")
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def build_index(force_rebuild: bool = False) -> None:
    """
    Build the FAISS index from the knowledge base.
    Idempotent: rebuilds only if not built yet or force_rebuild=True.
    """
    global _index, _kb
    if _index is not None and not force_rebuild:
        return

    _kb = _load_kb()
    model = _get_model()

    # Embed only the questions — retrieval is by question similarity.
    questions = [entry["question"] for entry in _kb]
    embeddings = model.encode(
        questions,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    ).astype("float32")

    _index = faiss.IndexFlatL2(EMBED_DIM)
    _index.add(embeddings)
    print(f"[rag] Index built with {len(_kb)} entries.")


def retrieve(query: str, k: int = 3) -> List[Dict[str, Any]]:
    """
    Retrieve the top-k most similar KB entries for a query.

    Returns a list of dicts:
        {id, category, question, answer, score}
    where score is cosine similarity in [0, 1] (1 = identical).

    Note: FAISS IndexFlatL2 returns squared L2 distance on
    normalized vectors, so similarity = 1 - (distance / 2).
    """
    build_index()
    if not query or not query.strip():
        return []

    model = _get_model()
    q_vec = model.encode(
        [query],
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    ).astype("float32")

    distances, indices = _index.search(q_vec, min(k, len(_kb)))

    results: List[Dict[str, Any]] = []
    for dist, idx in zip(distances[0], indices[0]):
        if idx < 0:
            continue
        entry = _kb[idx]
        # Convert squared L2 distance -> cosine similarity (normalized vecs).
        similarity = 1.0 - (float(dist) / 2.0)
        results.append(
            {
                "id": entry["id"],
                "category": entry["category"],
                "question": entry["question"],
                "answer": entry["answer"],
                "score": round(similarity, 4),
            }
        )
    return results


def get_top_score(query: str) -> float:
    """Convenience: return the top-1 similarity score, or 0.0 if no match."""
    hits = retrieve(query, k=1)
    return hits[0]["score"] if hits else 0.0


if __name__ == "__main__":
    # Smoke test if run directly.
    build_index()
    for q in ["Do you ship to Mumbai?", "Is the bottle dishwasher safe?"]:
        print(f"\nQuery: {q}")
        for hit in retrieve(q, k=3):
            print(f"  [{hit['score']}] {hit['question']}")