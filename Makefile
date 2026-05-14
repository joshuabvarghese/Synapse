# Synapse — SRE Incident Co-Pilot
# Usage: make up | make demo | make down | make reset

.PHONY: up down reset demo logs status

up:
	@echo "⬡  Starting Synapse..."
	@docker compose up -d
	@echo ""
	@echo "   Postgres + pgvector  → starting"
	@echo "   Ollama qwen2.5-coder:7b → pulling models on first run (~5 min)"
	@echo "   Streamlit app        → http://localhost:8501"
	@echo ""
	@echo "   Watching for app to be ready..."
	@until curl -sf http://localhost:8501/_stcore/health >/dev/null 2>&1; do sleep 2; printf '.'; done
	@echo ""
	@echo "✓  Synapse is live → http://localhost:8501"

down:
	docker compose down

# Wipe all data — fresh slate
reset:
	docker compose down -v
	@echo "✓  All volumes cleared — next 'make up' starts fresh"

# Follow app logs only (skip postgres/ollama noise)
logs:
	docker compose logs -f app

# Quick health check
status:
	@echo "--- Postgres ---"
	@docker compose exec postgres pg_isready -U ops -d synapse 2>/dev/null && echo "✓ up" || echo "✗ down"
	@echo "--- Ollama ---"
	@curl -sf http://localhost:11434/api/tags >/dev/null 2>&1 && echo "✓ up" || echo "✗ down (or starting)"
	@echo "--- App ---"
	@curl -sf http://localhost:8501/_stcore/health >/dev/null 2>&1 && echo "✓ up → http://localhost:8501" || echo "✗ down"
