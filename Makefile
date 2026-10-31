# QuantPulse developer entrypoints.
# Local Python work runs in this project's own virtualenv, `.venv` in the main checkout, which
# `make install` builds from uv.lock with the command CI and the images run (`uv sync --frozen
# --extra dev`), on the Python `.python-version` names. Until 2026-10-31 it was the monorepo's
# shared venv: about 870 packages against the lock's 230, so the laptop ran other versions than
# CI, loaded a dozen pytest plugins CI never had, and failed in ways CI could not see.
#
# The venv sits in the MAIN checkout, so resolving it from the CWD only works there. A git
# worktree lives under .claude/worktrees/<name> and has no venv of its own. Anchor on the main
# worktree instead — git reports it first from anywhere in the repo, worktrees included — and
# fall back to this directory when git can't answer (tarball export, no repo).
MAIN_WORKTREE := $(shell git worktree list --porcelain 2>/dev/null | sed -n '1s/^worktree //p')
ifeq ($(MAIN_WORKTREE),)
VENV_DIR := $(CURDIR)/.venv
else
VENV_DIR := $(MAIN_WORKTREE)/.venv
endif

VENV_PYTHON ?= $(VENV_DIR)/bin/python
VENV_BIN ?= $(VENV_DIR)/bin

# Anything that IMPORTS quantpulse at runtime needs this checkout's src ahead of the venv's
# editable .pth, which is a plain path entry pointing at the main checkout. Without it a
# worktree runs its own tests against the main checkout's source and passes green on code
# you never touched — a wrong answer, not an error. In the main checkout it names the very
# directory the .pth already points at, so it changes nothing there.
# ruff takes file paths and mypy resolves via mypy_path, so neither needs it.
VENV_PYTHON_SRC := PYTHONPATH=$(CURDIR)/src $(VENV_PYTHON)

.PHONY: install lock fmt lint type test test-all hooks build up up-build down ps status screenshots logs clean bootstrap dbt-build dbt-docs glossary

dbt-build:  ## Run dbt models + tests against local Postgres
	set -a && . ./.env && set +a && $(VENV_BIN)/dbt build --project-dir transform --profiles-dir transform

dbt-docs:  ## Generate and serve the dbt documentation site
	set -a && . ./.env && set +a && $(VENV_BIN)/dbt docs generate --project-dir transform --profiles-dir transform \
		&& $(VENV_BIN)/dbt docs serve --project-dir transform --profiles-dir transform --port 8081

bootstrap:  ## First-run seed: migrate, universe, backfill, features, train, score
	$(VENV_PYTHON_SRC) -m quantpulse.cli init-db
	$(VENV_PYTHON_SRC) -m quantpulse.cli sync-universe
	$(VENV_PYTHON_SRC) -m quantpulse.cli backfill
	$(VENV_PYTHON_SRC) -m quantpulse.cli features
	$(VENV_PYTHON_SRC) -m quantpulse.cli train
	$(VENV_PYTHON_SRC) -m quantpulse.cli score --replay

install:  ## Build or sync .venv to uv.lock exactly (removes anything the lock does not list)
	UV_PROJECT_ENVIRONMENT=$(VENV_DIR) uv sync --frozen --extra dev

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
	$(VENV_PYTHON_SRC) -m pytest -m "not integration"

test-all:  ## All tests incl. integration (needs `make up`)
	$(VENV_PYTHON_SRC) -m pytest

hooks:  ## Install pre-commit hooks into .git
	$(VENV_PYTHON) -m pre_commit install

build:  ## Build/rebuild all service images (run after changing app or Docker code)
	docker compose build

up:  ## Start the local stack (reuses existing images; run `make build` after code changes)
	docker compose up -d --wait

up-build:  ## Rebuild images then start the stack
	docker compose up -d --wait --build

down:  ## Stop the local stack (data volumes are kept)
	docker compose down

glossary:  ## Copy configs/glossary.yaml into the dashboard bundle (run after editing it)
	$(VENV_PYTHON) scripts/export_glossary.py

screenshots:  ## Regenerate the README's dashboard screenshots from the running stack (needs Chrome)
	$(VENV_PYTHON) scripts/screenshots.py

status:  ## Everything a check-in asks: stack, scheduled jobs, GitHub, data, decisions, dates ahead
	@scripts/status.sh

ps:  ## Show stack status
	docker compose ps

logs:  ## Tail stack logs
	docker compose logs -f --tail=100

clean:  ## Remove caches
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
	find . -type d -name __pycache__ -not -path "./node_modules/*" -exec rm -rf {} +

backup:  ## Snapshot the market database (options history + live record are unbackfillable)
	./scripts/backup-market.sh

# Gated on size: pruning costs the next build every layer step above the uv wheel cache,
# and running it weekly against a ~3 GB cache bought nothing but a slower Monday. Override
# the ceiling with PRUNE_CEILING_GB. Rationale in the script.
prune-cache:  ## Reclaim build cache above PRUNE_CEILING_GB (default 10) and superseded images; PRUNE_DRY_RUN=1 to preview
	./scripts/prune-cache.sh
