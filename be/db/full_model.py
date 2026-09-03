from datetime import datetime
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
    Enum,
)

from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from db.base import Base
from sqlalchemy.sql import func
import enum

# =========================================================
# 1. USER
# =========================================================


class UserORM(Base):
    __tablename__ = "users"

    id = Column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    username = Column(
        String,
        unique=True,
        nullable=True,
        index=True
    )

    email = Column(
        String,
        unique=True,
        nullable=True,
        index=True
    )

    google_subject = Column(
        String,
        unique=True,
        nullable=True,
        index=True,
    )

    profile_picture_url = Column(
        Text,
        nullable=True,
    )

    display_name = Column(
        String,
        nullable=True
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    last_login_at = Column(
        DateTime,
        nullable=True,
    )

    is_active = Column(
        Boolean,
        default=True
    )

    # Relationships
    conversations = relationship(
        "ConversationORM",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    memories = relationship(
        "UserMemoryORM",
        back_populates="user",
        cascade="all, delete-orphan"
    )


# =========================================================
# 2. CONVERSATION
# =========================================================

class ConversationORM(Base):
    __tablename__ = "conversations"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String, nullable=True)

    summary = Column(Text, nullable=True)
    conversation_state = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("UserORM", back_populates="conversations")

    messages = relationship("MessageORM",
        back_populates="conversation",
        cascade="all, delete-orphan"
    )


# =========================================================
# 3. MESSAGE
# =========================================================

class MessageORM(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)

    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=False, index=True)
    role = Column(String, nullable=False)
    # user
    # assistant
    # system
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    conversation = relationship("ConversationORM", back_populates="messages")


# =========================================================
# 4. USER MEMORY
# =========================================================
class UserMemoryORM(Base):
    __tablename__ = "user_memories"

    id = Column(Integer, primary_key=True, autoincrement=True)

    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)

    memory_type = Column(String, nullable=False)
    # travel_style, activity, budget, avoid, constraint, interest,
    # expertise, answer_length, tone, explanation_style, personal_fact

    content = Column(Text, nullable=False)
    embedding = Column(Vector(384), nullable=True)
    importance = Column(Float, default=0.5)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_accessed_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    # Relationships
    user = relationship("UserORM", back_populates="memories")


class KnowledgeGapORM(Base):
    __tablename__ = "knowledge_gaps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        String,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    conversation_id = Column(
        String,
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    query = Column(Text, nullable=False)
    rewritten_query = Column(Text, nullable=True)
    missing_requirements = Column(JSONB, nullable=False, default=list)
    recovery_queries = Column(JSONB, nullable=False, default=list)
    top_evidence = Column(JSONB, nullable=False, default=list)
    external_sources = Column(JSONB, nullable=False, default=list)
    external_recovery = Column(JSONB, nullable=False, default=dict)
    ingestion_status = Column(
        String, nullable=False, default="pending_review", index=True
    )
    status = Column(String, nullable=False, default="open", index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class PipelineTelemetryORM(Base):
    __tablename__ = "pipeline_telemetry"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(String, nullable=False, unique=True, index=True)
    user_id = Column(
        String,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    conversation_id = Column(
        String,
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status = Column(String, nullable=False, index=True)
    error_type = Column(String, nullable=True)
    total_latency_ms = Column(Float, nullable=False)
    total_tokens = Column(Integer, nullable=False, default=0)
    estimated_cost_usd = Column(Float, nullable=True)
    stage_records = Column(JSONB, nullable=False, default=list)
    token_totals = Column(JSONB, nullable=False, default=dict)
    pricing_snapshot = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class URLStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class URLSource(Base):
    __tablename__ = "url_sources"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    url = Column(String, unique=True, nullable=False)
    status = Column(Enum(URLStatus), default=URLStatus.PENDING, nullable=False)
    added_at = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey(
        "documents.id"), nullable=True)
    # Optional: store raw fetched HTML or cleaned markdown for reproducibility
    raw_html = Column(Text, nullable=True)

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

    latitude = Column(Float, nullable=True)

    longitude = Column(Float, nullable=True)

    geocoding_source = Column(Text, nullable=True)

    geocoded_at = Column(DateTime(timezone=True), nullable=True)
    # AI-supported metadata
    ai_summary = Column(Text, nullable=True)

    ai_topic = Column(Text, nullable=True)

    ai_tags = Column(
        ARRAY(String),
        nullable=True,
    )

    ai_activities = Column(
        ARRAY(String),
        nullable=True,
    )

    ai_travel_styles = Column(
        ARRAY(String),
        nullable=True,
    )

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
