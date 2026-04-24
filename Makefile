# ── Synapse · Makefile ────────────────────────────────────────────────────────
# Usage:  make up | make down | make reset | make logs | make status | make lint
# ─────────────────────────────────────────────────────────────────────────────

.PHONY: up down reset logs status shell lint fmt help

# Coloured output helpers
BOLD  := \033[1m
RESET := \033[0m
GREEN := \033[32m
CYAN  := \033[36m
RED   := \033[31m

## ── Core ────────────────────────────────────────────────────────────────────

up:           ## Start all services (builds app image if needed)
	@echo "$(BOLD)⬡  Starting Synapse…$(RESET)"
	@docker compose up -d --build
	@echo ""
	@echo "  $(CYAN)postgres + pgvector$(RESET)      → starting"
	@echo "  $(CYAN)ollama qwen2.5-coder:7b$(RESET)  → pulling on first run (~5 min)"
	@echo "  $(CYAN)streamlit app$(RESET)             → http://localhost:8501"
	@echo ""
	@printf "  Waiting for app to be ready "
	@until curl -sf http://localhost:8501/_stcore/health >/dev/null 2>&1; do sleep 2; printf '.'; done
	@echo ""
	@echo "  $(GREEN)✓  Synapse is live → http://localhost:8501$(RESET)"

down:         ## Stop all services (data volumes preserved)
	docker compose down

reset:        ## Wipe all volumes and start fresh
	docker compose down -v
	@echo "$(GREEN)✓  All volumes cleared. Run 'make up' to start fresh.$(RESET)"

## ── Observability ───────────────────────────────────────────────────────────

logs:         ## Follow app logs (Ctrl+C safe — services keep running)
	docker compose logs -f app

logs-all:     ## Follow all service logs
	docker compose logs -f

status:       ## Quick health check for all services
	@echo "$(BOLD)--- Postgres ---$(RESET)"
	@docker compose exec postgres pg_isready -U ops -d synapse 2>/dev/null \
		&& echo "$(GREEN)✓ up$(RESET)" || echo "$(RED)✗ down$(RESET)"
	@echo "$(BOLD)--- Ollama ---$(RESET)"
	@curl -sf http://localhost:11434/api/tags >/dev/null 2>&1 \
		&& echo "$(GREEN)✓ up$(RESET)" || echo "$(RED)✗ down (or starting)$(RESET)"
	@echo "$(BOLD)--- App ---$(RESET)"
	@curl -sf http://localhost:8501/_stcore/health >/dev/null 2>&1 \
		&& echo "$(GREEN)✓ up → http://localhost:8501$(RESET)" || echo "$(RED)✗ down$(RESET)"

## ── Development ─────────────────────────────────────────────────────────────

shell:        ## Open a psql shell into the synapse database
	docker compose exec postgres psql -U ops -d synapse

shell-app:    ## Open a bash shell in the running app container
	docker compose exec app bash

lint:         ## Run ruff linter over app/
	ruff check app/

fmt:          ## Auto-format app/ with ruff
	ruff format app/

## ── Help ────────────────────────────────────────────────────────────────────

help:         ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-14s$(RESET) %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
