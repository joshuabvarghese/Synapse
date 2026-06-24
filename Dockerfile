# ─────────────────────────────────────────────────────────────────────────────
# Synapse — Monolithic image for Hugging Face Spaces (CPU Basic tier)
#
# Three services, one container:
#   • PostgreSQL 16 + pgvector  ─ vector + full-text search
#   • Ollama (CPU)              ─ LLM inference + embeddings
#   • Streamlit                 ─ the app UI on port 7860
#
# Build time: ~15 min on first push (downloads ~2 GB of models).
# After that HF caches the image, so cold starts are fast.
# ─────────────────────────────────────────────────────────────────────────────
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    # ── Postgres (all local — single container) ───────────────────────────────
    POSTGRES_HOST=localhost \
    POSTGRES_USER=ops \
    POSTGRES_PASSWORD=ops \
    POSTGRES_DB=synapse \
    # ── Ollama ────────────────────────────────────────────────────────────────
    OLLAMA_HOST=http://localhost:11434 \
    # qwen2.5-coder:3b gives a good quality/speed trade-off on 2 vCPUs.
    # Swap to qwen2.5-coder:0.5b below (and in the RUN pull step) for ~3x
    # faster responses if you prioritise speed over reasoning depth.
    OLLAMA_MODEL=qwen2.5-coder:3b \
    EMBED_MODEL=nomic-embed-text \
    KB_DIR=/kb


# ── Base system packages ──────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        gnupg curl wget ca-certificates lsb-release \
        build-essential git \
        python3.11 python3-pip python3.11-dev \
    && rm -rf /var/lib/apt/lists/*


# ── PostgreSQL 16 (official PGDG repo) ───────────────────────────────────────
RUN curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
        | gpg --dearmor -o /etc/apt/trusted.gpg.d/postgresql.gpg \
    && echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        postgresql-16 postgresql-server-dev-16 libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Allow all local TCP connections without a password (single-container demo)
RUN echo "host all all 127.0.0.1/32 trust" >> /etc/postgresql/16/main/pg_hba.conf \
    && echo "host all all ::1/128      trust" >> /etc/postgresql/16/main/pg_hba.conf


# ── pgvector 0.7.0 ───────────────────────────────────────────────────────────
RUN git clone --branch v0.7.0 https://github.com/pgvector/pgvector.git /tmp/pgvector \
    && cd /tmp/pgvector \
    && PG_CONFIG=/usr/lib/postgresql/16/bin/pg_config make \
    && PG_CONFIG=/usr/lib/postgresql/16/bin/pg_config make install \
    && rm -rf /tmp/pgvector


# ── Ollama ────────────────────────────────────────────────────────────────────
RUN curl -fsSL https://ollama.ai/install.sh | sh


# ── Bake models into the image ────────────────────────────────────────────────
# Models are downloaded once at build time and stored in /root/.ollama/models.
# This avoids a 2 GB cold-start download every time the Space wakes up.
RUN ollama serve & \
    until curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; do sleep 2; done \
    && ollama pull qwen2.5-coder:3b \
    && ollama pull nomic-embed-text \
    && pkill ollama || true


# ── Python app ────────────────────────────────────────────────────────────────
WORKDIR /app
COPY app/requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY app/ .

# Ensure KB_FALLBACK_DIR (/app/kb) exists so knowledge_base.py never errors
RUN mkdir -p /app/kb


# ── Knowledge base & DB schema ────────────────────────────────────────────────
RUN mkdir -p /kb
COPY kb/ /kb/
COPY init.sql /app/init.sql


# ── Startup script ────────────────────────────────────────────────────────────
COPY start_hf.sh /start.sh
RUN chmod +x /start.sh


EXPOSE 7860

CMD ["/start.sh"]
