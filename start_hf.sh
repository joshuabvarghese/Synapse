#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# Synapse — container startup for Hugging Face Spaces
#
# Boot order: PostgreSQL → schema bootstrap → Ollama → Streamlit
# ─────────────────────────────────────────────────────────────────────────────
set -e

echo ""
echo "  ⬡  Synapse — SRE Incident Co-Pilot"
echo "  ─────────────────────────────────────────────"
echo "  Agentic · Hybrid Search · Multi-turn · Offline"
echo ""


# ── 1. PostgreSQL ─────────────────────────────────────────────────────────────
echo "  → Starting PostgreSQL 16..."

# The cluster was already initialised by apt at image-build time.
# pg_ctlcluster is Ubuntu's wrapper around pg_ctl.
pg_ctlcluster 16 main start

# Wait until the socket is accepting connections
until su -s /bin/bash postgres -c "pg_isready -q" 2>/dev/null; do
    sleep 1
    printf '.'
done
echo "  ✓ PostgreSQL ready"


# ── 2. Bootstrap database (idempotent) ───────────────────────────────────────
echo "  → Bootstrapping database..."

# Create role (ignore error if it already exists)
su -s /bin/bash postgres -c \
    "psql postgres -c \"CREATE ROLE ops WITH LOGIN PASSWORD 'ops';\" 2>/dev/null || true"

# Create database
su -s /bin/bash postgres -c \
    "psql postgres -c \"CREATE DATABASE synapse OWNER ops;\" 2>/dev/null || true"

# Install extensions + schema
su -s /bin/bash postgres -c \
    "psql synapse -c \"CREATE EXTENSION IF NOT EXISTS vector;\"  2>/dev/null || true"
su -s /bin/bash postgres -c \
    "psql synapse -c \"CREATE EXTENSION IF NOT EXISTS pg_trgm;\" 2>/dev/null || true"
su -s /bin/bash postgres -c \
    "psql synapse -f /app/init.sql 2>/dev/null || true"

echo "  ✓ Schema ready"


# ── 3. Ollama ─────────────────────────────────────────────────────────────────
echo "  → Starting Ollama (models pre-loaded in image)..."
ollama serve &

until curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; do
    sleep 2
    printf '.'
done
echo "  ✓ Ollama ready"


# ── 4. Streamlit ──────────────────────────────────────────────────────────────
echo ""
echo "  ✓ All services up → http://localhost:7860"
echo ""

cd /app
exec streamlit run main.py \
    --server.port=7860 \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --browser.gatherUsageStats=false \
    --theme.base=dark
