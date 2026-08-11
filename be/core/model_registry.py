from __future__ import annotations

from sentence_transformers import CrossEncoder, SentenceTransformer

EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
RERANKER_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"

_embedding_model: SentenceTransformer | None = None
_reranker: CrossEncoder | None = None


def load_models() -> None:
    global _embedding_model, _reranker

    if _embedding_model is None:
        _embedding_model = SentenceTransformer(
            EMBEDDING_MODEL_NAME
        )

    if _reranker is None:
        _reranker = CrossEncoder(
            RERANKER_MODEL_NAME
        )


def unload_models() -> None:
    global _embedding_model, _reranker
    _embedding_model = None
    _reranker = None


def get_embedding_model() -> SentenceTransformer:
    if _embedding_model is None:
        raise RuntimeError(
            "Embedding model is not loaded. "
            "Run the app through FastAPI lifespan."
        )
    return _embedding_model


def get_reranker() -> CrossEncoder:
    if _reranker is None:
        raise RuntimeError(
            "Reranker model is not loaded. "
            "Run the app through FastAPI lifespan."
        )
    return _reranker
