#!/bin/bash
set -e

echo ""
echo "  ⬡  Synapse — SRE Incident Co-Pilot"
echo "  ───────────────────────────────────────────"
echo "  Agentic · Hybrid Search · Multi-turn · Offline"
echo ""

if ! docker info >/dev/null 2>&1; then
  echo "  ✗  Docker is not running. Please start Docker and retry."
  exit 1
fi

echo "  → Starting services..."
docker compose up -d

echo ""
echo "  → Waiting for Postgres..."
until docker compose exec -T postgres pg_isready -U "${POSTGRES_USER:-ops}" -d "${POSTGRES_DB:-synapse}" >/dev/null 2>&1; do
  sleep 1; printf '.'
done
echo " ✓"

echo "  → Waiting for Ollama + models (first run pulls ~5GB — grab a coffee)..."
MODEL="${OLLAMA_MODEL:-qwen2.5-coder:7b}"
TRIES=0
until curl -sf http://localhost:11434/api/tags 2>/dev/null | grep -q "${MODEL%%:*}"; do
  sleep 5; printf '.'
  TRIES=$((TRIES+1))
  if [ "$TRIES" -ge 72 ]; then   # 6-minute hard timeout
    echo ""
    echo "  ✗  Timed out waiting for Ollama. Check logs: docker compose logs ollama"
    exit 1
  fi
done
echo " ✓"

echo "  → Waiting for Streamlit..."
until curl -sf http://localhost:8501/_stcore/health >/dev/null 2>&1; do
  sleep 2; printf '.'
done
echo " ✓"

echo ""
echo "  ✓  Synapse is live → http://localhost:8501"
echo ""
echo "  What's new in v2:"
echo "    • Agent loop — model calls tools, diagnoses, applies fix, verifies"
echo "    • qwen2.5-coder:7b — better commands, better reasoning"
echo "    • Hybrid search — pgvector cosine + Postgres FTS fused with RRF"
echo "    • Multi-turn — ask follow-up questions after each incident"
echo "    • Auto-embed — drop .md files into kb/ and they index live"
echo ""
echo "  Press Ctrl+C to stop watching logs (services keep running)"
echo "  Run './stop.sh' to shut everything down"
echo ""

docker compose logs -f app
