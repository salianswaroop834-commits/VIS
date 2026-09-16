-- ============================================================================
-- Supabase Migration: 02_pgvector_rag.sql
-- Vehicle Insurance Knowledge Base with pgvector Semantic Retrieval
-- ============================================================================

-- 1. Enable pgvector extension for dense similarity search
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Create Knowledge Embeddings Store
CREATE TABLE IF NOT EXISTS knowledge_embeddings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_title VARCHAR(255) NOT NULL,
    category VARCHAR(50) NOT NULL,
    chunk_index INT NOT NULL,
    content TEXT NOT NULL,
    embedding vector(384) NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_document_chunk UNIQUE (document_title, chunk_index)
);

-- 3. Approximate Nearest Neighbor Index for Cosine Distance
CREATE INDEX IF NOT EXISTS idx_knowledge_embeddings_cosine 
ON knowledge_embeddings USING ivfflat (embedding vector_cosine_ops) 
WITH (lists = 50);

-- 4. Vector Cosine Similarity Search Function (RPC for Supabase client)
CREATE OR REPLACE FUNCTION match_knowledge_chunks(
    query_embedding vector(384),
    match_threshold float DEFAULT 0.20,
    match_count int DEFAULT 5
)
RETURNS TABLE (
    id UUID,
    document_title VARCHAR,
    category VARCHAR,
    chunk_index INT,
    content TEXT,
    similarity FLOAT
)
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    RETURN QUERY
    SELECT
        k.id,
        k.document_title,
        k.category,
        k.chunk_index,
        k.content,
        ROUND((1 - (k.embedding <=> query_embedding))::numeric, 4)::float AS similarity
    FROM knowledge_embeddings k
    WHERE (1 - (k.embedding <=> query_embedding)) > match_threshold
    ORDER BY k.embedding <=> query_embedding ASC
    LIMIT match_count;
END;
$$;

-- 5. Row Level Security
ALTER TABLE knowledge_embeddings ENABLE ROW LEVEL SECURITY;

-- Allow read-only access for anonymous and authenticated callers
DROP POLICY IF EXISTS "Allow read access to knowledge embeddings" ON knowledge_embeddings;
CREATE POLICY "Allow read access to knowledge embeddings"
    ON knowledge_embeddings
    FOR SELECT
    USING (true);

-- Restrict write/update/delete to service role only
DROP POLICY IF EXISTS "Restrict modifications to service role" ON knowledge_embeddings;
CREATE POLICY "Restrict modifications to service role"
    ON knowledge_embeddings
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);
