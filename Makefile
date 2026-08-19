# Founder Engagement Workflow — Redesign Health take-home
# docs/PLAN.md v2.1 (FROZEN) is the source of truth.

PY_BIN ?= python3.13
VENV   := .venv
PY     := $(VENV)/bin/python
PIP    := $(VENV)/bin/pip

.PHONY: setup test eval api ui seed data clean env-check ai-plan ai-connectivity ai-initial

setup: $(VENV)/.stamp ## create venv, install backend deps, install frontend deps
	@echo "--- setup complete ---"
	@$(PY) --version
	@$(PY) -c "import fastapi,pydantic,sqlalchemy,yaml,rapidfuzz,pytest; print('backend deps ok')"
	@if [ -d frontend ]; then cd frontend && npm install --silent && echo "frontend deps ok"; fi

$(VENV)/.stamp: backend/requirements.txt
	$(PY_BIN) -m venv $(VENV)
	$(PIP) install --quiet --upgrade pip
	$(PIP) install --quiet -r backend/requirements.txt
	@touch $(VENV)/.stamp

data: ## regenerate the synthetic load population (800 profiles, seeded)
	$(PY) scripts/gen_load_population.py --n 800 --seed 20260819

test: ## unit + API tests (no API key required)
	$(VENV)/bin/pytest backend/tests -q

eval: ## deterministic evaluation on the golden set -> docs/EVAL_REPORT.md
	$(PY) scripts/eval.py

seed: ## build SQLite DB from the assessed load population
	$(PY) scripts/seed.py

# Local secrets live in `.env` (gitignored). Sourced only if it exists; the
# deterministic targets above never need it.
ENVLOAD = set -a; [ -f .env ] && . ./.env; set +a;

api: ## run FastAPI on :8000  (loads .env if present)
	$(ENVLOAD) $(VENV)/bin/uvicorn app.api.main:app --reload --port 8000 --app-dir backend

env-check: ## show which LLM provider is configured — prints NO secret value
	@$(ENVLOAD) PYTHONPATH=backend $(PY) -c "\
import os; from app.llm.provider import configured_provider, default_adapter; \
a = default_adapter(); \
print('LLM_PROVIDER      :', os.environ.get('LLM_PROVIDER') or '(unset -> inferred)'); \
print('provider          :', configured_provider()); \
print('adapter           :', type(a).__name__); \
print('OPENAI_API_KEY set:', bool(os.environ.get('OPENAI_API_KEY'))); \
print('OPENAI_MODEL      :', os.environ.get('OPENAI_MODEL') or '(default)'); \
print('available         :', a.available()); \
print('detail            :', getattr(a, 'last_error', None) or 'ok')"

ai-plan: ## show the bounded real-provider plan + budgets. NO network request.
	$(ENVLOAD) $(PY) scripts/openai_eval.py --dry-run

ai-connectivity: ## REAL OpenAI — EXACTLY 1 paid call. Needs a key.
	$(ENVLOAD) $(PY) scripts/openai_eval.py --connectivity --max-calls 1

ai-initial: ## REAL OpenAI — the remaining 4 paid calls. Needs a key.
	$(ENVLOAD) $(PY) scripts/openai_eval.py --initial --max-calls 4

ui: ## run Vite dev server on :5173
	cd frontend && npm run dev

clean:
	rm -rf $(VENV) backend/**/__pycache__ .pytest_cache founder.db
