-- ── Synapse · schema.sql ──────────────────────────────────────────────────────
-- Runs automatically on first Postgres boot via docker-entrypoint-initdb.d/.
-- Fully idempotent — safe to run multiple times.
-- ─────────────────────────────────────────────────────────────────────────────

-- pgvector extension (bundled in pgvector/pgvector:pg16 image)
CREATE EXTENSION IF NOT EXISTS vector;


-- ── system_logs ───────────────────────────────────────────────────────────────
-- Ring buffer of structured log events injected by demo scenarios.
-- In a real deployment this would be populated by a Fluent Bit / Vector pipeline.

CREATE TABLE IF NOT EXISTS system_logs (
    id          BIGSERIAL    PRIMARY KEY,
    ts          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    level       TEXT         NOT NULL CHECK (level IN ('ERROR','WARN','INFO','DEBUG')),
    service     TEXT         NOT NULL,
    host        TEXT,
    message     TEXT         NOT NULL,
    status_code INT,
    latency_ms  INT,
    trace_id    TEXT
);

CREATE INDEX IF NOT EXISTS idx_logs_ts      ON system_logs (ts DESC);
CREATE INDEX IF NOT EXISTS idx_logs_service ON system_logs (service);
CREATE INDEX IF NOT EXISTS idx_logs_level   ON system_logs (level);
CREATE INDEX IF NOT EXISTS idx_logs_svc_ts  ON system_logs (service, ts DESC);


-- ── incident_kb ───────────────────────────────────────────────────────────────
-- Incident runbooks with:
--   • 768-dim HNSW vector index for semantic search (nomic-embed-text)
--   • GIN tsvector index for full-text search
--   • Both fused at query time via Reciprocal Rank Fusion (RRF)

CREATE TABLE IF NOT EXISTS incident_kb (
    id          BIGSERIAL    PRIMARY KEY,
    inc_id      TEXT         UNIQUE NOT NULL,   -- e.g. "INC-2024-0312"
    title       TEXT         NOT NULL,
    service     TEXT         NOT NULL,
    severity    TEXT         NOT NULL DEFAULT 'P2' CHECK (severity IN ('P0','P1','P2','P3')),
    tags        TEXT[]       NOT NULL DEFAULT '{}',
    resolution  TEXT         NOT NULL,
    source_file TEXT,
    embedding   VECTOR(768),                    -- nomic-embed-text output dim
    fts_vector  TSVECTOR,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- HNSW index: fast approximate nearest-neighbour over cosine distance.
-- m=16, ef_construction=64 are good defaults for ~10K vectors.
CREATE INDEX IF NOT EXISTS idx_kb_hnsw
    ON incident_kb USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- GIN index: fast full-text search over pre-computed tsvector.
CREATE INDEX IF NOT EXISTS idx_kb_fts     ON incident_kb USING gin (fts_vector);
CREATE INDEX IF NOT EXISTS idx_kb_service ON incident_kb (service);
CREATE INDEX IF NOT EXISTS idx_kb_severity ON incident_kb (severity);


-- Trigger: auto-compute tsvector on INSERT / UPDATE.
-- Combines title + resolution + tags so all fields are searchable.
CREATE OR REPLACE FUNCTION fn_kb_fts_update() RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
    NEW.fts_vector :=
        setweight(to_tsvector('english', coalesce(NEW.title, '')),      'A') ||
        setweight(to_tsvector('english', coalesce(array_to_string(NEW.tags, ' '), '')), 'B') ||
        setweight(to_tsvector('english', coalesce(NEW.resolution, '')), 'C');
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_kb_fts ON incident_kb;
CREATE TRIGGER trg_kb_fts
    BEFORE INSERT OR UPDATE ON incident_kb
    FOR EACH ROW EXECUTE FUNCTION fn_kb_fts_update();


-- ── resolution_log ────────────────────────────────────────────────────────────
-- Audit trail: every time the agent resolves an incident, we record it.
-- Useful for MTTR trending and retrospectives.

CREATE TABLE IF NOT EXISTS resolution_log (
    id           BIGSERIAL    PRIMARY KEY,
    scenario_key TEXT         NOT NULL,
    severity     TEXT,
    service      TEXT,
    alert_text   TEXT         NOT NULL,
    resolution   TEXT,
    tool_steps   INT          NOT NULL DEFAULT 0,
    duration_ms  INT,
    resolved_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_res_log_ts  ON resolution_log (resolved_at DESC);
CREATE INDEX IF NOT EXISTS idx_res_log_svc ON resolution_log (service);
