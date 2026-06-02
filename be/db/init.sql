CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS rag_chunks (
    id UUID PRIMARY KEY,

    document_title TEXT,
    section_heading TEXT,
    subsection_heading TEXT,

    chunk_text TEXT NOT NULL,

    place_name TEXT,
    city TEXT,
    province TEXT,

    place_type TEXT,
    chunk_topic TEXT,

    tags TEXT[],

    source_file TEXT,

    embedding VECTOR(384),

    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_place_type
ON rag_chunks(place_type);

CREATE INDEX IF NOT EXISTS idx_city
ON rag_chunks(city);

CREATE INDEX IF NOT EXISTS idx_tags
ON rag_chunks USING GIN(tags);

CREATE INDEX IF NOT EXISTS idx_embedding
ON rag_chunks
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);