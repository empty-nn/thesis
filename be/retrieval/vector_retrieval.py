# retrieval/retrieval_service.py

from typing import List

from sqlalchemy import text
from sqlalchemy.orm import Session

from sentence_transformers import (
    SentenceTransformer,
    CrossEncoder,
)

from langchain_core.documents import Document
from langchain_community.retrievers import BM25Retriever

from db.session import SessionLocal
from db.full_model import RagChunkORM


# =========================================================
# EMBEDDING MODEL
# =========================================================

EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"

embedding_model = SentenceTransformer(
    EMBEDDING_MODEL_NAME
)


# =========================================================
# RERANKER
# =========================================================

reranker = CrossEncoder(
    "cross-encoder/ms-marco-MiniLM-L-6-v2"
)


# =========================================================
# QUERY UNDERSTANDING
# =========================================================

def extract_query_metadata(query: str):

    lower = query.lower()

    metadata = {
        "city": None,
        "travel_style": None,
    }

    # =====================================================
    # CITY DETECTION
    # =====================================================

    known_cities = [
        "da nang",
        "hanoi",
        "hoi an",
        "hue",
        "saigon",
        "ho chi minh",
    ]

    for city in known_cities:

        if city in lower:
            metadata["city"] = city.title()

    # =====================================================
    # TRAVEL STYLE
    # =====================================================

    if "family" in lower:
        metadata["travel_style"] = "family"

    if "luxury" in lower:
        metadata["travel_style"] = "luxury"

    if "adventure" in lower:
        metadata["travel_style"] = "adventure"

    if "culture" in lower:
        metadata["travel_style"] = "culture"

    return metadata


# =========================================================
# VECTOR SEARCH
# =========================================================

def vector_search(
    query: str,
    limit: int = 10,
):
    """
    PostgreSQL pgvector similarity search
    """

    db: Session = SessionLocal()

    try:

        query_embedding = embedding_model.encode(
            query
        ).tolist()

        extracted = extract_query_metadata(
            query
        )

        city_filter = extracted["city"]

        # =================================================
        # FILTERED VECTOR SEARCH
        # =================================================

        if city_filter:

            sql = text(
                """
                SELECT
                    *,
                    embedding <=> CAST(:embedding AS vector)
                    AS distance

                FROM rag_chunks

                WHERE LOWER(city) = LOWER(:city)

                ORDER BY embedding <=> CAST(:embedding AS vector)

                LIMIT :limit
                """
            )

            params = {
                "embedding": query_embedding,
                "city": city_filter,
                "limit": limit,
            }

        else:

            sql = text(
                """
                SELECT
                    *,
                    embedding <=> CAST(:embedding AS vector)
                    AS distance

                FROM rag_chunks

                ORDER BY embedding <=> CAST(:embedding AS vector)

                LIMIT :limit
                """
            )

            params = {
                "embedding": query_embedding,
                "limit": limit,
            }

        rows = db.execute(
            sql,
            params,
        ).fetchall()

        return rows

    finally:
        db.close()


# =========================================================
# DB ROW -> LANGCHAIN DOCUMENT
# =========================================================

def row_to_document(row) -> Document:

    return Document(

        page_content=row.chunk_text,

        metadata={

            "chunk_id": str(row.id),

            "city": row.city,

            "province": row.province,

            "place_name": row.place_name,

            "place_type": row.place_type,

            "chunk_topic": row.ai_topic,

            "ai_tags": row.ai_tags,

            "ai_activities": row.ai_activities,

            "ai_travel_styles": row.ai_travel_styles,

            "distance": (
                float(row.distance)
                if hasattr(row, "distance")
                else None
            ),
        },
    )


# =========================================================
# BM25 SEARCH
# =========================================================

def bm25_search(
    query: str,
    limit: int = 10,
):

    db: Session = SessionLocal()

    try:

        extracted = extract_query_metadata(
            query
        )

        city_filter = extracted["city"]

        query_builder = db.query(
            RagChunkORM
        )

        # =================================================
        # METADATA FILTERING
        # =================================================

        if city_filter:

            query_builder = query_builder.filter(
                RagChunkORM.city.ilike(city_filter)
            )

        rows = query_builder.all()

        documents = [
            row_to_document(row)
            for row in rows
        ]

        retriever = BM25Retriever.from_documents(
            documents
        )

        retriever.k = limit

        results = retriever.invoke(
            query
        )

        return results

    finally:
        db.close()


# =========================================================
# RERANK DOCUMENTS
# =========================================================

def rerank_documents(
    query: str,
    documents: List[Document],
    top_k: int = 5,
):

    pairs = [
        (query, doc.page_content)
        for doc in documents
    ]

    scores = reranker.predict(
        pairs
    )

    ranked = sorted(
        zip(documents, scores),
        key=lambda x: x[1],
        reverse=True,
    )

    final_documents = [
        doc
        for doc, score in ranked[:top_k]
    ]

    return final_documents


# =========================================================
# HYBRID SEARCH
# =========================================================

def hybrid_search(
    query: str,
    vector_limit: int = 10,
    bm25_limit: int = 10,
    rerank_top_k: int = 5,
):
    """
    Hybrid Retrieval:
    - Vector Search
    - BM25
    - Score Fusion
    - Reranking
    """

    # =====================================================
    # VECTOR SEARCH
    # =====================================================

    vector_rows = vector_search(
        query=query,
        limit=vector_limit,
    )

    vector_documents = [
        row_to_document(row)
        for row in vector_rows
    ]

    # =====================================================
    # BM25 SEARCH
    # =====================================================

    bm25_documents = bm25_search(
        query=query,
        limit=bm25_limit,
    )

    # =====================================================
    # SCORE FUSION
    # =====================================================

    scored = {}

    # VECTOR SCORE
    for rank, doc in enumerate(vector_documents):

        key = doc.page_content

        score = 1 / (rank + 1)

        if key not in scored:

            scored[key] = {
                "doc": doc,
                "score": 0,
            }

        scored[key]["score"] += score

    # BM25 SCORE
    for rank, doc in enumerate(bm25_documents):

        key = doc.page_content

        score = 1 / (rank + 1)

        if key not in scored:

            scored[key] = {
                "doc": doc,
                "score": 0,
            }

        scored[key]["score"] += score

    # =====================================================
    # SORT BY FUSION SCORE
    # =====================================================

    ranked = sorted(
        scored.values(),
        key=lambda x: x["score"],
        reverse=True,
    )

    merged_documents = [
        item["doc"]
        for item in ranked
    ]

    # =====================================================
    # RERANKING
    # =====================================================

    final_documents = rerank_documents(
        query=query,
        documents=merged_documents,
        top_k=rerank_top_k,
    )

    return final_documents


# =========================================================
# MAIN TEST
# =========================================================

if __name__ == "__main__":

    query = (
        "family-friendly activities in Da Nang, Vietnam"
    )

    results = hybrid_search(
        query=query,
        vector_limit=10,
        bm25_limit=10,
        rerank_top_k=5,
    )

    print("\nTOP CHUNKS:\n")

    for i, doc in enumerate(results):

        print("=" * 80)

        print(f"RESULT {i+1}")

        print("\nMETADATA:")
        print(doc.metadata)

        print("\nCONTENT:")
        print(doc.page_content[:500])

        print("\n")