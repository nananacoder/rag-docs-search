-- Phase 2 schema — source of truth (phase2-selfbuilt.md §3).
-- Applied via Cloud SQL Studio (or psql/docker for local dev); idempotent
-- via IF NOT EXISTS guards. No migration framework by design (§2.5 ADR).

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;   -- optional, fuzzy proper-noun matching

-- One row per book (one OpenStax part = one book_id)
CREATE TABLE IF NOT EXISTS books (
  book_id       TEXT PRIMARY KEY,
  title         TEXT NOT NULL,
  author        TEXT NOT NULL,
  year          INT,
  gcs_uri       TEXT NOT NULL,
  page_count    INT,
  source        TEXT,                     -- e.g. 'openstax'
  ingested_at   TIMESTAMPTZ DEFAULT now(),
  content_hash  TEXT
);

-- One row per chapter (or major section)
CREATE TABLE IF NOT EXISTS chapters (
  chapter_id    BIGSERIAL PRIMARY KEY,
  book_id       TEXT REFERENCES books(book_id) ON DELETE CASCADE,
  ordinal       INT,                      -- chapter 1,2,3...
  title         TEXT,                     -- "Chapter 22: Stars from Adolescence to Old Age"
  start_page    INT,
  end_page      INT,
  UNIQUE (book_id, ordinal)
);

-- One row per chunk.
-- content        = verbatim source text — what citations display / bbox highlights.
-- context_prefix = M3 Contextual Retrieval situating context (NULL until M3).
-- Retrieval (embedding + BM25) sees context_prefix || content; display sees content.
-- content_tsv is GENERATED so ingestion can never forget to maintain it.
CREATE TABLE IF NOT EXISTS chunks (
  chunk_id       BIGSERIAL PRIMARY KEY,
  book_id        TEXT NOT NULL REFERENCES books(book_id) ON DELETE CASCADE,
  chapter_id     BIGINT REFERENCES chapters(chapter_id),
  page           INT,
  bbox           JSONB,                   -- {x0,y0,x1,y1} from Document AI
  modality       TEXT CHECK (modality IN ('text','table','figure','diagram')),
  content        TEXT NOT NULL,
  context_prefix TEXT,
  content_tsv    tsvector GENERATED ALWAYS AS
                   (to_tsvector('english', coalesce(context_prefix, '') || ' ' || content)) STORED,
  embedding      vector(768),             -- Gemini Embedding 2, output_dimensionality=768 (MRL)
  token_count    INT,
  created_at     TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw
  ON chunks USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS chunks_tsv_gin   ON chunks USING GIN (content_tsv);
CREATE INDEX IF NOT EXISTS chunks_book      ON chunks (book_id);
CREATE INDEX IF NOT EXISTS chunks_chapter   ON chunks (chapter_id);
CREATE INDEX IF NOT EXISTS chunks_book_page ON chunks (book_id, page);
