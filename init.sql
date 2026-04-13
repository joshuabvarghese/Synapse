-- synapse schema v2
-- Changes: vector(768) for nomic-embed-text, FTS tsvector, GIN index

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS system_logs (
    id          BIGSERIAL   PRIMARY KEY,
    ts          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    level       VARCHAR(5)  NOT NULL,
    service     VARCHAR(50) NOT NULL,
    host        VARCHAR(50) NOT NULL DEFAULT 'localhost',
    message     TEXT        NOT NULL,
    status_code SMALLINT    DEFAULT 0,
    latency_ms  REAL        DEFAULT 0,
    trace_id    VARCHAR(32) DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_logs_ts    ON system_logs (ts DESC);
CREATE INDEX IF NOT EXISTS idx_logs_level ON system_logs (level, ts DESC);
CREATE INDEX IF NOT EXISTS idx_logs_svc   ON system_logs (service, ts DESC);

CREATE TABLE IF NOT EXISTS incident_kb (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    inc_id      VARCHAR(30) NOT NULL UNIQUE,
    title       TEXT        NOT NULL,
    service     VARCHAR(50) NOT NULL,
    severity    VARCHAR(3)  NOT NULL DEFAULT 'P2',
    tags        TEXT[]      NOT NULL DEFAULT '{}',
    resolution  TEXT        NOT NULL,
    source_file VARCHAR(255) DEFAULT '',
    embedding   vector(768),
    fts_vector  tsvector GENERATED ALWAYS AS (
        to_tsvector('english',
            coalesce(inc_id,'')  || ' ' ||
            coalesce(title,'')   || ' ' ||
            coalesce(service,'') || ' ' ||
            coalesce(resolution,'')
        )
    ) STORED,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_kb_embedding
    ON incident_kb USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_kb_fts
    ON incident_kb USING gin(fts_vector);
