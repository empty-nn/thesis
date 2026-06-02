# db/models.py

import uuid

from sqlalchemy import (
    ARRAY,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    literal_column,
)

from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from pgvector.sqlalchemy import Vector

from db.base import Base


# =========================================================
# DOCUMENT TABLE
# =========================================================

class Document(Base):
    __tablename__ = "documents"

    # Primary key
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Source information
    title = Column(Text, nullable=True)

    document_type = Column(Text, nullable=True)
    # pdf, html, docx, markdown, blog, api

    source_type = Column(Text, nullable=True)
    # official_site, tourism_blog, travel_api, manual_upload

    source_name = Column(Text, nullable=True)

    source_url = Column(Text, nullable=True)

    source_file = Column(Text, nullable=True)

    # Content
    raw_content = Column(Text, nullable=True)

    cleaned_markdown = Column(Text, nullable=True)

    # General metadata
    country = Column(Text, nullable=True)

    language = Column(Text, nullable=True)
    # en, vi, etc.

    # Processing status
    ingestion_status = Column(
        Text,
        nullable=False,
        default="raw",
    )
    # raw, cleaned, chunked, embedded, failed

    chunk_count = Column(Integer, nullable=True)

    embedding_model = Column(Text, nullable=True)

    verified = Column(
        Boolean,
        nullable=False,
        default=False,
    )

    # Flexible metadata
    extra_metadata = Column(JSONB, nullable=True)

    # Timestamp
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationship
    chunks = relationship(
        "RagChunkORM",
        back_populates="document",
        cascade="all, delete-orphan",
    )


# =========================================================
# RAG CHUNK TABLE
# =========================================================

class RagChunkORM(Base):
    __tablename__ = "rag_chunks"

    # Primary key
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # FK to document
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    document = relationship(
        "Document",
        back_populates="chunks",
    )

    # Chunk identity
    chunk_index = Column(
        Integer,
        nullable=False,
    )

    chunk_hash = Column(
        String(64),
        nullable=True,
        index=True,
    )
    # SHA-256 hash of normalized chunk_text.
    # Used to detect duplicate chunks.
    # Do NOT make this globally unique for now.

    source_chunk_id = Column(
        Text,
        nullable=True,
        index=True,
    )
    # Example:
    # page_3_chunk_2
    # section_intro_chunk_1
    # html_main_content_5

    # Chunk structure
    section_heading = Column(Text, nullable=True)

    subsection_heading = Column(Text, nullable=True)

    section_level = Column(Integer, nullable=True)

    # Chunk content
    chunk_text = Column(
        Text,
        nullable=False,
    )

    word_count = Column(Integer, nullable=True)

    # Basic location metadata
    country = Column(Text, nullable=True, index=True)

    city = Column(Text, nullable=True, index=True)

    province = Column(Text, nullable=True, index=True)

    place_name = Column(Text, nullable=True)

    place_type = Column(Text, nullable=True, index=True)
    # beach, restaurant, museum, hotel, mountain, city_overview, etc.

    # AI-supported metadata
    ai_summary = Column(Text, nullable=True)

    ai_topic = Column(Text, nullable=True)

    ai_tags = Column(
        ARRAY(String),
        nullable=True,
    )
    # beach, food, culture, nature, family, nightlife

    ai_activities = Column(
        ARRAY(String),
        nullable=True,
    )
    # swimming, sightseeing, hiking, eating, photography

    ai_travel_styles = Column(
        ARRAY(String),
        nullable=True,
    )
    # budget, luxury, adventure, relaxation, cultural

    ai_suitable_for = Column(
        ARRAY(String),
        nullable=True,
    )
    # families, couples, solo_travelers, backpackers

    ai_metadata = Column(JSONB, nullable=True)
    # Flexible AI output.
    # Example:
    # {
    #   "best_time": "morning",
    #   "estimated_cost_level": "cheap",
    #   "reason": "Suitable for sightseeing and food tourism",
    #   "confidence_notes": "City is explicit, cost is inferred"
    # }

    metadata_source = Column(Text, nullable=True)
    # source_text, ai_inferred, manual, api

    metadata_confidence = Column(Float, nullable=True)
    # 0.0 - 1.0

    # Embedding
    embedding = Column(
        Vector(384),
        nullable=True,
    )

    embedding_model = Column(Text, nullable=True)

    # Quality
    quality_score = Column(Float, nullable=True)
    # 0.0 - 1.0

    importance_score = Column(Float, nullable=True)
    # 0.0 - 1.0

    verified = Column(
        Boolean,
        nullable=False,
        default=False,
    )

    # Flexible metadata
    extra_metadata = Column(JSONB, nullable=True)

    # Timestamp
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Indexes and constraints
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "chunk_index",
            name="uq_rag_chunks_document_chunk_index",
        ),

        # Vector search index
        Index(
            "ix_rag_chunks_embedding",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_with={"lists": 100},
            postgresql_ops={
                "embedding": "vector_cosine_ops",
            },
        ),

        # Full-text search index
        Index(
            "ix_rag_chunks_search_vector",
            func.to_tsvector(
                literal_column("'english'"),
                chunk_text,
            ),
            postgresql_using="gin",
        ),

        # AI metadata indexes
        Index(
            "ix_rag_chunks_ai_tags",
            "ai_tags",
            postgresql_using="gin",
        ),

        Index(
            "ix_rag_chunks_ai_activities",
            "ai_activities",
            postgresql_using="gin",
        ),

        Index(
            "ix_rag_chunks_ai_travel_styles",
            "ai_travel_styles",
            postgresql_using="gin",
        ),

        Index(
            "ix_rag_chunks_ai_suitable_for",
            "ai_suitable_for",
            postgresql_using="gin",
        ),

        # Common filter indexes
        Index(
            "ix_rag_chunks_city_place_type",
            "city",
            "place_type",
        ),

        Index(
            "ix_rag_chunks_country_city",
            "country",
            "city",
        ),
    )