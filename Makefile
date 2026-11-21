# solodesk: `make run` is all you need. It installs what is missing, then starts the app.
PYTHON ?= python3
VENV := .venv
BIN := $(VENV)/bin
# Run a command with the variables from .env. The file is parsed as data (python-dotenv),
# never by the shell, so a password with spaces, $ or & is just a password.
ENV := $(BIN)/dotenv run --

.DEFAULT_GOAL := run
.PHONY: dev run build seed test lint e2e

# A failed install removes the half-made venv, so the next try with PYTHON=... starts clean.
$(VENV): backend/pyproject.toml
	@$(PYTHON) -c 'import sys; sys.exit(sys.version_info < (3, 12))' 2>/dev/null || { \
	  echo "solodesk needs Python 3.12 or newer, and '$(PYTHON)' is older or missing."; \
	  echo "Name a newer one, for example: make $(or $(MAKECMDGOALS),run) PYTHON=python3.12"; \
	  exit 1; }
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --quiet -c backend/constraints.txt -e "backend[dev]" || { rm -rf $(VENV); exit 1; }
	@touch $(VENV)

frontend/node_modules: frontend/package-lock.json
	cd frontend && npm ci
	@touch frontend/node_modules

.env:
	cp .env.example .env
	@echo "Created .env with the example password. Change SOLODESK_PASSWORD before real use."

## dev: API with reload on :4150 and the UI with hot reload on http://localhost:4151
dev: $(VENV) frontend/node_modules .env
	@trap 'kill 0' INT TERM EXIT; \
	$(ENV) $(BIN)/uvicorn solodesk.main:create_app --factory --reload --reload-dir backend --port 4150 & \
	(cd frontend && npm run dev) & \
	wait

build: frontend/node_modules
	cd frontend && npm run build

## run: the built app, API and UI together, on http://localhost:4150
run: $(VENV) build .env
	@$(ENV) $(BIN)/uvicorn solodesk.main:create_app --factory --port 4150

## seed: fill an empty database with demo data
seed: $(VENV) .env
	@$(ENV) $(BIN)/python -m solodesk.seed

test: $(VENV) frontend/node_modules
	cd backend && ../$(BIN)/pytest -q
	cd frontend && npm test && npm run typecheck

lint: $(VENV)
	cd backend && ../$(BIN)/ruff check . && ../$(BIN)/ruff format --check .

## e2e: Playwright smoke test against the built app (needs `npx playwright install chromium` once)
e2e: $(VENV) build
	cd frontend && npm run e2e
