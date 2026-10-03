CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS document_chunks (
    id BIGSERIAL PRIMARY KEY,
    source TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding VECTOR(3072) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Use exact cosine search for the local runbook corpus. The default Gemini
-- vectors have 3072 dimensions; pgvector HNSW's vector type supports at most
-- 2000. Creating that index here aborts initialization on a fresh database.
