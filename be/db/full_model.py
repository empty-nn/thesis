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

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    document_type = Column(Text, nullable=False, index=True)
    # pdf, html, docx, markdown

    source_location = Column(Text, nullable=True, index=True)
    # HTML: normalized URL
    # PDF: saved file path

    file_hash = Column(String(64), nullable=True, index=True)
    # PDF/DOCX/uploaded file duplicate check

    raw_markdown = Column(Text, nullable=True)
    cleaned_markdown = Column(Text, nullable=True)
    ingestion_status = Column(
        Text,
        nullable=False,
        default="raw",
        index=True,
    )

    extraction_method = Column(Text, nullable=True)
    chunking_method = Column(Text, nullable=True)
    embedding_model = Column(Text, nullable=True)

    language = Column(Text, nullable=True, index=True)

    verified = Column(
        Boolean,
        nullable=False,
        default=False,
    )

    extra_metadata = Column(JSONB, nullable=True)

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

    chunks = relationship(
        "RagChunkORM",
        back_populates="document",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "document_type",
            "source_location",
            name="uq_documents_type_source_location",
        ),
        UniqueConstraint(
            "document_type",
            "file_hash",
            name="uq_documents_type_file_hash",
        ),
    )
# =========================================================
# RAG CHUNK TABLE
# =========================================================

class RagChunkORM(Base):
    __tablename__ = "rag_chunks"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

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

    chunk_index = Column(Integer, nullable=False)

    chunk_hash = Column(
        String(64),
        nullable=False,
        index=True,
    )
    chunk_text = Column(Text, nullable=False)
    word_count = Column(Integer, nullable=True)

    # Citation / display support
    section_heading = Column(Text, nullable=True)

    page_number = Column(Integer, nullable=True)

    # Location metadata
    country = Column(Text, nullable=True, index=True)
    city = Column(Text, nullable=True, index=True)
    province = Column(Text, nullable=True, index=True)
    place_name = Column(Text, nullable=True, index=True)
    place_type = Column(Text, nullable=True, index=True)

    # AI-supported metadata
    ai_summary = Column(Text, nullable=True)
    ai_topic = Column(Text, nullable=True)
    ai_tags = Column(ARRAY(String), nullable=True,)
    ai_activities = Column(ARRAY(String), nullable=True,)
    ai_travel_styles = Column(ARRAY(String), nullable=True,)

    ai_suitable_for = Column(
        ARRAY(String),
        nullable=True,
    )

    ai_metadata = Column(JSONB, nullable=True)
    # Embedding
    embedding = Column(
        Vector(384),
        nullable=True,
    )

    embedding_model = Column(Text, nullable=True)
    importance_score = Column(Float, nullable=True)

    verified = Column(
        Boolean,
        nullable=False,
        default=False,
    )

    extra_metadata = Column(JSONB, nullable=True)

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

    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "chunk_index",
            name="uq_rag_chunks_document_chunk_index",
        ),

        UniqueConstraint(
            "document_id",
            "chunk_hash",
            name="uq_rag_chunks_document_chunk_hash",
        ),

        Index(
            "ix_rag_chunks_embedding",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_with={"lists": 100},
            postgresql_ops={
                "embedding": "vector_cosine_ops",
            },
        ),

        Index(
            "ix_rag_chunks_search_vector",
            func.to_tsvector(
                literal_column("'english'"),
                chunk_text,
            ),
            postgresql_using="gin",
        ),

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