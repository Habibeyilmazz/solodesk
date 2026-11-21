# solodesk: `make dev` is all you need. It installs what is missing, then starts the app.
PYTHON ?= python3
VENV := .venv
BIN := $(VENV)/bin
# Put the variables from .env into the environment of a recipe.
ENV := set -a; . ./.env; set +a;

.PHONY: dev run build seed test lint e2e

$(VENV): backend/pyproject.toml
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --quiet -e "backend[dev]"
	@touch $(VENV)

frontend/node_modules: frontend/package-lock.json
	cd frontend && npm ci
	@touch frontend/node_modules

.env:
	cp .env.example .env
	@echo "Created .env with the example password. Change SOLODESK_PASSWORD before real use."

## dev: API with reload on :4150 and the UI with hot reload on http://localhost:4151
dev: $(VENV) frontend/node_modules .env
	@$(ENV) trap 'kill 0' INT TERM EXIT; \
	$(BIN)/uvicorn solodesk.main:create_app --factory --reload --reload-dir backend --port 4150 & \
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
