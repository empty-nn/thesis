from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlparse

import numpy as np
from langchain_core.documents import Document
from langchain_community.retrievers import BM25Retriever
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from core.model_registry import (
    get_embedding_model,
    get_reranker,
    reranker_enabled,
)
from schemas.pipeline import (
    ParsedQuery,
    UserTravelMemory,
)
from db.full_model import Document as DocumentORM, RagChunkORM
from db.session import SessionLocal


@dataclass
class RetrievalFilters:
    city: str | None = None
    cities: list[str] = field(default_factory=list)
    province: str | None = None
    country: str | None = None

    place_types: list[str] = field(
        default_factory=list
    )


def build_retrieval_filters(
    parsed: ParsedQuery,
) -> RetrievalFilters:
    # Broad, multi-aspect requests need cross-type evidence. Keep their place
    # types as fusion metadata signals instead of restrictive SQL predicates.
    hard_place_type_intents = {
        "attraction_search",
        "accommodation_search",
        "food_search",
        "event_search",
    }
    return RetrievalFilters(
        country=parsed.location.country,
        city=parsed.location.city,
        cities=parsed.location.cities,
        province=parsed.location.province,
        place_types=(
            parsed.place_types
            if parsed.intent in hard_place_type_intents
            else []
        ),
    )


def _source_location_from_orm(row) -> str | None:
    document = getattr(
        row,
        "document",
        None,
    )

    if document is None:
        return None

    return getattr(
        document,
        "source_location",
        None,
    )


def row_to_document(row) -> Document:
    source_location = getattr(
        row,
        "source_location",
        None,
    )

    if source_location is None:
        source_location = (
            _source_location_from_orm(row)
        )

    distance = getattr(
        row,
        "distance",
        None,
    )

    vector_distance = (
        float(distance)
        if distance is not None
        else None
    )

    # pgvector <=> is cosine distance.
    # Convert to cosine similarity for easier UI interpretation.
    vector_score = (
        1.0 - vector_distance
        if vector_distance is not None
        else None
    )

    return Document(
        page_content=row.chunk_text,
        metadata={
            "chunk_id": str(row.id),
            "document_id": (
                str(row.document_id)
                if getattr(
                    row,
                    "document_id",
                    None,
                )
                else None
            ),

            "country": getattr(
                row,
                "country",
                None,
            ),
            "city": getattr(
                row,
                "city",
                None,
            ),
            "province": getattr(
                row,
                "province",
                None,
            ),

            "place_name": getattr(
                row,
                "place_name",
                None,
            ),
            "place_type": getattr(
                row,
                "place_type",
                None,
            ),

            "section_heading": getattr(
                row,
                "section_heading",
                None,
            ),
            "chunk_topic": getattr(
                row,
                "ai_topic",
                None,
            ),
            "ai_summary": getattr(
                row,
                "ai_summary",
                None,
            ),

            "ai_tags": getattr(
                row,
                "ai_tags",
                None,
            ) or [],
            "ai_activities": getattr(
                row,
                "ai_activities",
                None,
            ) or [],
            "ai_travel_styles": getattr(
                row,
                "ai_travel_styles",
                None,
            ) or [],
            "ai_suitable_for": getattr(
                row,
                "ai_suitable_for",
                None,
            ) or [],

            "source_location": (
                str(source_location)
                if source_location
                else None
            ),

            "vector_distance": vector_distance,
            "vector_score": vector_score,

            "source_date": getattr(
                row,
                "source_date",
                None,
            ),
            "updated_at": getattr(
                row,
                "updated_at",
                None,
            ),
            "latitude": getattr(
                row,
                "latitude",
                None,
            ),
            "longitude": getattr(
                row,
                "longitude",
                None,
            ),
        },
    )


def vector_search(
    query: str,
    filters: RetrievalFilters,
    limit: int = 30,
) -> list[Document]:
    db: Session = SessionLocal()

    try:
        query_embedding = (
            get_embedding_model()
            .encode(query)
            .tolist()
        )

        where_parts = [
            "rc.embedding IS NOT NULL"
        ]

        params = {
            "embedding": query_embedding,
            "limit": limit,
        }

        # These filters mirror the intended metadata-aware search.
        if filters.country:
            where_parts.append(
                "LOWER(rc.country) = LOWER(:country)"
            )
            params["country"] = filters.country

        if filters.cities:
            where_parts.append(
                "LOWER(rc.city) = ANY(:cities)"
            )
            params["cities"] = [city.lower() for city in filters.cities]

        if filters.province:
            where_parts.append(
                "LOWER(rc.province) = LOWER(:province)"
            )
            params["province"] = filters.province

        if filters.place_types:
            where_parts.append(
                "rc.place_type = ANY(:place_types)"
            )
            params["place_types"] = (
                filters.place_types
            )

        where_sql = " AND ".join(
            where_parts
        )

        # Join documents only so the API can return a usable citation/source URL.
        sql = text(
            f"""
            SELECT
                rc.*,
                d.source_location AS source_location,
                rc.embedding <=> CAST(:embedding AS vector)
                    AS distance
            FROM rag_chunks AS rc
            LEFT JOIN documents AS d
                ON d.id = rc.document_id
            WHERE {where_sql}
            ORDER BY
                rc.embedding <=> CAST(:embedding AS vector)
            LIMIT :limit
            """
        )

        rows = db.execute(
            sql,
            params,
        ).fetchall()

        return [
            row_to_document(row)
            for row in rows
        ]

    finally:
        db.close()


def _build_bm25_document(row) -> Document:
    original_doc = row_to_document(
        row
    )

    bm25_text_parts: list[str] = []

    if getattr(
        row,
        "place_name",
        None,
    ):
        bm25_text_parts.append(
            f"Place: {row.place_name}"
        )

    if getattr(
        row,
        "ai_summary",
        None,
    ):
        bm25_text_parts.append(
            row.ai_summary
        )

    if getattr(
        row,
        "chunk_text",
        None,
    ):
        bm25_text_parts.append(
            row.chunk_text
        )

    return Document(
        page_content="\n".join(
            bm25_text_parts
        ),
        metadata=original_doc.metadata,
    )


def bm25_search(
    query: str,
    filters: RetrievalFilters,
    limit: int = 30,
) -> list[Document]:
    db: Session = SessionLocal()

    try:
        query_builder = (
            db.query(
                RagChunkORM.id.label("id"),
                RagChunkORM.document_id.label("document_id"),
                RagChunkORM.chunk_text.label("chunk_text"),
                RagChunkORM.section_heading.label("section_heading"),
                RagChunkORM.country.label("country"),
                RagChunkORM.city.label("city"),
                RagChunkORM.province.label("province"),
                RagChunkORM.place_name.label("place_name"),
                RagChunkORM.place_type.label("place_type"),
                RagChunkORM.latitude.label("latitude"),
                RagChunkORM.longitude.label("longitude"),
                RagChunkORM.ai_summary.label("ai_summary"),
                RagChunkORM.ai_topic.label("ai_topic"),
                RagChunkORM.ai_tags.label("ai_tags"),
                RagChunkORM.ai_activities.label("ai_activities"),
                RagChunkORM.ai_travel_styles.label("ai_travel_styles"),
                RagChunkORM.ai_suitable_for.label("ai_suitable_for"),
                RagChunkORM.updated_at.label("updated_at"),
                DocumentORM.source_location.label("source_location"),
            )
            .outerjoin(
                DocumentORM,
                DocumentORM.id == RagChunkORM.document_id,
            )
        )

        if filters.country:
            query_builder = (
                query_builder.filter(
                    RagChunkORM.country.ilike(
                        filters.country
                    )
                )
            )

        if filters.cities:
            query_builder = (
                query_builder.filter(
                    func.lower(RagChunkORM.city).in_(
                        [city.lower() for city in filters.cities]
                    )
                )
            )

        if filters.province:
            query_builder = (
                query_builder.filter(
                    RagChunkORM.province.ilike(
                        filters.province
                    )
                )
            )

        if filters.place_types:
            query_builder = (
                query_builder.filter(
                    RagChunkORM.place_type.in_(
                        filters.place_types
                    )
                )
            )

        rows = query_builder.all()

        if not rows:
            return []

        documents = [
            _build_bm25_document(row)
            for row in rows
        ]

        # Keep LangChain's BM25Retriever from the notebook, but inspect its
        # underlying vectorizer so the debug UI receives the real BM25 score.
        retriever = (
            BM25Retriever.from_documents(
                documents
            )
        )

        processed_query = (
            retriever.preprocess_func(query)
        )

        scores = np.asarray(
            retriever.vectorizer.get_scores(
                processed_query
            ),
            dtype=float,
        )

        ranked_indices = (
            np.argsort(scores)[::-1][:limit]
        )

        results: list[Document] = []

        for index in ranked_indices:
            doc = documents[int(index)]
            doc.metadata[
                "bm25_score"
            ] = float(scores[int(index)])
            results.append(doc)

        return results

    finally:
        db.close()


def metadata_boost(
    doc: Document,
    parsed: ParsedQuery,
    memory: UserTravelMemory,
) -> float:
    score = 0.0
    metadata = doc.metadata

    doc_styles = set(
        metadata.get(
            "ai_travel_styles",
            [],
        )
    )

    doc_activities = set(
        metadata.get(
            "ai_activities",
            [],
        )
    )

    doc_suitable = set(
        metadata.get(
            "ai_suitable_for",
            [],
        )
    )

    for style in parsed.travel_styles:
        if style in doc_styles:
            score += 0.015

    for activity in parsed.activities:
        if activity in doc_activities:
            score += 0.015

    for suitable in parsed.suitable_for:
        if suitable in doc_suitable:
            score += 0.015

    for style in (
        memory.preferred_travel_styles
    ):
        if style in doc_styles:
            score += 0.005

    for activity in memory.preferred_activities:
        if activity in doc_activities:
            score += 0.005

    return score


def haversine_distance_km(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    earth_radius = 6371.0

    lat1 = math.radians(lat1)
    lat2 = math.radians(lat2)

    delta_lat = lat2 - lat1
    delta_lon = math.radians(
        lon2 - lon1
    )

    a = (
        math.sin(
            delta_lat / 2
        ) ** 2
        + math.cos(lat1)
        * math.cos(lat2)
        * math.sin(
            delta_lon / 2
        ) ** 2
    )

    c = 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a),
    )

    return earth_radius * c


def geo_boost(
    doc: Document,
    target_lat: float | None,
    target_lon: float | None,
) -> float:
    if (
        target_lat is None
        or target_lon is None
    ):
        return 0.0

    lat = doc.metadata.get(
        "latitude"
    )
    lon = doc.metadata.get(
        "longitude"
    )

    if lat is None or lon is None:
        return 0.0

    distance = haversine_distance_km(
        target_lat,
        target_lon,
        float(lat),
        float(lon),
    )

    doc.metadata[
        "geo_distance_km"
    ] = distance

    return 0.02 / (
        1 + distance
    )


def freshness_boost(
    doc: Document,
    max_boost: float = 0.01,
) -> float:
    date_value = (
        doc.metadata.get(
            "source_date"
        )
        or doc.metadata.get(
            "updated_at"
        )
    )

    if not date_value:
        return 0.0

    if isinstance(
        date_value,
        str,
    ):
        try:
            date_value = (
                datetime.fromisoformat(
                    date_value.replace(
                        "Z",
                        "+00:00",
                    )
                )
            )
        except ValueError:
            return 0.0

    if date_value.tzinfo is None:
        date_value = (
            date_value.replace(
                tzinfo=timezone.utc
            )
        )

    now = datetime.now(
        timezone.utc
    )

    age_days = max(
        (now - date_value).days,
        0,
    )

    decay = math.exp(
        -age_days / 365
    )

    return max_boost * decay


def fuse_results(
    vector_docs: list[Document],
    bm25_docs: list[Document],
    parsed: ParsedQuery,
    memory: UserTravelMemory,
    rrf_k: int = 60,
    target_lat: float | None = None,
    target_lon: float | None = None,
) -> list[Document]:
    scored: dict[
        str,
        dict,
    ] = {}

    for rank, doc in enumerate(
        vector_docs,
        start=1,
    ):
        chunk_id = doc.metadata[
            "chunk_id"
        ]

        if chunk_id not in scored:
            scored[chunk_id] = {
                "doc": doc,
                "score": 0.0,
                "vector_rank": None,
                "bm25_rank": None,
            }

        scored[chunk_id][
            "score"
        ] += 1 / (
            rrf_k + rank
        )

        scored[chunk_id][
            "vector_rank"
        ] = rank

    for rank, doc in enumerate(
        bm25_docs,
        start=1,
    ):
        chunk_id = doc.metadata[
            "chunk_id"
        ]

        if chunk_id not in scored:
            scored[chunk_id] = {
                "doc": doc,
                "score": 0.0,
                "vector_rank": None,
                "bm25_rank": None,
            }
        else:
            # Preserve BM25 diagnostics even if the canonical document
            # originated from vector search.
            scored[chunk_id][
                "doc"
            ].metadata[
                "bm25_score"
            ] = doc.metadata.get(
                "bm25_score"
            )

            if (
                not scored[chunk_id]["doc"]
                .metadata.get(
                    "source_location"
                )
            ):
                scored[chunk_id][
                    "doc"
                ].metadata[
                    "source_location"
                ] = doc.metadata.get(
                    "source_location"
                )

        scored[chunk_id][
            "score"
        ] += 1 / (
            rrf_k + rank
        )

        scored[chunk_id][
            "bm25_rank"
        ] = rank

    for item in scored.values():
        doc = item["doc"]

        meta_score = metadata_boost(
            doc=doc,
            parsed=parsed,
            memory=memory,
        )

        geo_score = geo_boost(
            doc=doc,
            target_lat=target_lat,
            target_lon=target_lon,
        )

        fresh_score = (
            freshness_boost(
                doc=doc
            )
        )

        item["score"] += (
            meta_score
            + geo_score
            + fresh_score
        )

        item[
            "metadata_boost"
        ] = meta_score
        item[
            "geo_boost"
        ] = geo_score
        item[
            "freshness_boost"
        ] = fresh_score

    ranked = sorted(
        scored.values(),
        key=lambda item: item[
            "score"
        ],
        reverse=True,
    )

    results: list[Document] = []

    for item in ranked:
        doc = item["doc"]

        doc.metadata[
            "fusion_score"
        ] = item["score"]
        doc.metadata[
            "vector_rank"
        ] = item["vector_rank"]
        doc.metadata[
            "bm25_rank"
        ] = item["bm25_rank"]
        doc.metadata[
            "metadata_boost"
        ] = item[
            "metadata_boost"
        ]
        doc.metadata[
            "geo_boost"
        ] = item[
            "geo_boost"
        ]
        doc.metadata[
            "freshness_boost"
        ] = item[
            "freshness_boost"
        ]

        results.append(doc)

    return results


def rerank_documents(
    query: str,
    documents: list[Document],
    top_k: int = 8,
) -> list[Document]:
    if not documents:
        return []

    if not reranker_enabled():
        # The candidates already arrive in reciprocal-rank-fusion order. Keep
        # that ordering on memory-constrained deployments where loading a
        # second transformer model would exceed the instance limit.
        return documents[:top_k]

    pairs = [
        (
            query,
            doc.page_content,
        )
        for doc in documents
    ]

    scores = (
        get_reranker()
        .predict(pairs)
    )

    scored: list[
        tuple[
            Document,
            float,
        ]
    ] = []

    for doc, score in zip(
        documents,
        scores,
    ):
        score = float(score)

        doc.metadata[
            "rerank_score"
        ] = score

        scored.append(
            (doc, score)
        )

    scored.sort(
        key=lambda item: item[1],
        reverse=True,
    )

    return [
        doc
        for doc, _ in scored[:top_k]
    ]


def source_name(
    source_location: str | None,
) -> str:
    if not source_location:
        return "Unknown source"

    parsed = urlparse(
        source_location
    )

    if (
        parsed.scheme
        and parsed.netloc
    ):
        return parsed.netloc

    return (
        source_location
        .replace("\\", "/")
        .rstrip("/")
        .split("/")[-1]
        or "Source"
    )
