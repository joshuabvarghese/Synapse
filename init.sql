-- Synapse v4 — PostgreSQL schema initialisation
-- Run automatically by docker-entrypoint-initdb.d on first start.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ── Knowledge base ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS incident_kb (
    id          SERIAL PRIMARY KEY,
    inc_id      TEXT        NOT NULL UNIQUE,
    title       TEXT        NOT NULL,
    service     TEXT        NOT NULL DEFAULT 'unknown',
    severity    TEXT        NOT NULL DEFAULT 'P2',
    tags        TEXT[]      NOT NULL DEFAULT '{}',
    resolution  TEXT        NOT NULL DEFAULT '',
    source_file TEXT        NOT NULL DEFAULT 'manual',
    embedding   vector(768),
    fts_vector  tsvector GENERATED ALWAYS AS (
                    to_tsvector('english', coalesce(title, '') || ' ' || coalesce(resolution, ''))
                ) STORED,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS incident_kb_embedding_idx
    ON incident_kb USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 50);

CREATE INDEX IF NOT EXISTS incident_kb_fts_idx
    ON incident_kb USING gin(fts_vector);

CREATE INDEX IF NOT EXISTS incident_kb_service_idx
    ON incident_kb (service);

-- ── System logs ───────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS system_logs (
    id          BIGSERIAL   PRIMARY KEY,
    ts          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    level       TEXT        NOT NULL CHECK (level IN ('ERROR', 'WARN', 'INFO')),
    service     TEXT        NOT NULL,
    host        TEXT        NOT NULL DEFAULT 'unknown',
    message     TEXT        NOT NULL,
    status_code INTEGER,
    latency_ms  INTEGER,
    trace_id    TEXT
);

CREATE INDEX IF NOT EXISTS system_logs_ts_idx ON system_logs (ts DESC);
CREATE INDEX IF NOT EXISTS system_logs_service_idx ON system_logs (service);
CREATE INDEX IF NOT EXISTS system_logs_level_idx ON system_logs (level);

-- ── Incident history (MTTR tracking) ─────────────────────────────────────────

CREATE TABLE IF NOT EXISTS incident_history (
    id           BIGSERIAL   PRIMARY KEY,
    scenario_key TEXT        NOT NULL,
    service      TEXT        NOT NULL,
    severity     TEXT        NOT NULL DEFAULT 'P2',
    mttr_minutes INTEGER     NOT NULL,
    resolved_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS incident_history_resolved_at_idx
    ON incident_history (resolved_at DESC);

CREATE INDEX IF NOT EXISTS incident_history_service_severity_idx
    ON incident_history (service, severity);
