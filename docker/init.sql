-- docker/init.sql
-- Runs automatically on first Postgres container start.
-- Enables pgvector so we can store resume + JD embeddings.

CREATE EXTENSION IF NOT EXISTS vector;

-- Verify
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
    RAISE NOTICE 'pgvector extension enabled successfully.';
  END IF;
END $$;
