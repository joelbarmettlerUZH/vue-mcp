-- Schema for vue-docs-mcp shared data layer.
-- Executed by PostgreSQL container on first start via /docker-entrypoint-initdb.d/.

CREATE TABLE IF NOT EXISTS pages (
    path        TEXT PRIMARY KEY,
    content     TEXT NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS entities (
    name        TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    page_path   TEXT NOT NULL DEFAULT '',
    section     TEXT NOT NULL DEFAULT '',
    related     JSONB NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS synonyms (
    alias        TEXT PRIMARY KEY,
    entity_names JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS index_state (
    file_path        TEXT PRIMARY KEY,
    content_hash     TEXT NOT NULL,
    pipeline_version TEXT NOT NULL,
    chunk_ids        JSONB NOT NULL DEFAULT '[]',
    last_indexed     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS models (
    name       TEXT PRIMARY KEY,
    data       BYTEA NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
