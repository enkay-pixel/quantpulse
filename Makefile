# QuantPulse developer entrypoints.
# Local Python work uses the monorepo's shared virtualenv unless VENV_PYTHON is overridden.
VENV_PYTHON ?= ../../.venv/bin/python

.PHONY: install lock fmt lint type test test-all hooks up down ps logs clean bootstrap dbt-build dbt-docs

VENV_BIN ?= ../../.venv/bin

dbt-build:  ## Run dbt models + tests against local Postgres
	set -a && . ./.env && set +a && $(VENV_BIN)/dbt build --project-dir transform --profiles-dir transform

dbt-docs:  ## Generate and serve the dbt documentation site
	set -a && . ./.env && set +a && $(VENV_BIN)/dbt docs generate --project-dir transform --profiles-dir transform \
		&& $(VENV_BIN)/dbt docs serve --project-dir transform --profiles-dir transform --port 8081

bootstrap:  ## First-run seed: migrate, universe, backfill, features, train, score
	$(VENV_PYTHON) -m quantpulse.cli init-db
	$(VENV_PYTHON) -m quantpulse.cli sync-universe
	$(VENV_PYTHON) -m quantpulse.cli backfill
	$(VENV_PYTHON) -m quantpulse.cli features
	$(VENV_PYTHON) -m quantpulse.cli train
	$(VENV_PYTHON) -m quantpulse.cli score --replay

install:  ## Install the package + dev tools into the shared venv
	uv pip install -e ".[dev]" --python $(VENV_PYTHON)

lock:  ## Re-resolve and pin all dependencies
	uv lock

fmt:  ## Auto-format and fix lint issues
	$(VENV_PYTHON) -m ruff format src tests
	$(VENV_PYTHON) -m ruff check --fix src tests

lint:  ## Check formatting and lint (CI mode, no changes)
	$(VENV_PYTHON) -m ruff format --check src tests
	$(VENV_PYTHON) -m ruff check src tests

type:  ## Static type check
	$(VENV_PYTHON) -m mypy

test:  ## Fast unit tests (no external services)
	$(VENV_PYTHON) -m pytest -m "not integration"

test-all:  ## All tests incl. integration (needs `make up`)
	$(VENV_PYTHON) -m pytest

hooks:  ## Install pre-commit hooks into .git
	$(VENV_PYTHON) -m pre_commit install

up:  ## Start the local stack
	docker compose up -d --wait

down:  ## Stop the local stack (data volumes are kept)
	docker compose down

ps:  ## Show stack status
	docker compose ps

logs:  ## Tail stack logs
	docker compose logs -f --tail=100

clean:  ## Remove caches
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
	find . -type d -name __pycache__ -not -path "./node_modules/*" -exec rm -rf {} +
