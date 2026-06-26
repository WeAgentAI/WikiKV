CREATE EXTENSION IF NOT EXISTS ltree;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS pages (
    id BIGSERIAL PRIMARY KEY,
    wiki_key TEXT NOT NULL,
    bizuin TEXT NOT NULL,
    path TEXT NOT NULL UNIQUE,
    ltree_path LTREE NOT NULL,
    parent_path TEXT,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('dir', 'file')),
    content TEXT NOT NULL DEFAULT '',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    size BIGINT NOT NULL DEFAULT 0,
    mtime TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pages_wiki_key ON pages (wiki_key);
CREATE INDEX IF NOT EXISTS idx_pages_bizuin ON pages (bizuin);
CREATE INDEX IF NOT EXISTS idx_pages_parent_path ON pages (parent_path);
CREATE INDEX IF NOT EXISTS idx_pages_ltree_path ON pages USING GIST (ltree_path);
CREATE INDEX IF NOT EXISTS idx_pages_path_trgm ON pages USING GIN (path gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_pages_metadata ON pages USING GIN (metadata);

CREATE OR REPLACE FUNCTION set_pages_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_pages_updated_at ON pages;
CREATE TRIGGER trg_pages_updated_at
BEFORE UPDATE ON pages
FOR EACH ROW
EXECUTE FUNCTION set_pages_updated_at();
