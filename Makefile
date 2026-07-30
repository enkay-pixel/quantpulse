# QuantPulse developer entrypoints.
# Local Python work uses the monorepo's shared virtualenv unless VENV_PYTHON is overridden.
#
# The venv sits two levels above the MAIN checkout (<monorepo>/projects/quantpulse), so
# resolving it from the CWD only works there. A git worktree lives under
# .claude/worktrees/<name>, where ../../.venv resolves to <checkout>/.claude/.venv and
# every target dies with "No such file or directory". Anchor on the main worktree instead
# — git reports it first from anywhere in the repo, worktrees included — and keep the old
# relative path as the fallback for when git can't answer (tarball export, no repo).
MAIN_WORKTREE := $(shell git worktree list --porcelain 2>/dev/null | sed -n '1s/^worktree //p')
ifeq ($(MAIN_WORKTREE),)
VENV_ROOT := ../..
else
VENV_ROOT := $(abspath $(MAIN_WORKTREE)/../..)
endif

VENV_PYTHON ?= $(VENV_ROOT)/.venv/bin/python
VENV_BIN ?= $(VENV_ROOT)/.venv/bin

# Anything that IMPORTS quantpulse at runtime needs this checkout's src ahead of the venv's
# editable .pth, which is a plain path entry pointing at the main checkout. Without it a
# worktree runs its own tests against the main checkout's source and passes green on code
# you never touched — a wrong answer, not an error. In the main checkout it names the very
# directory the .pth already points at, so it changes nothing there.
# ruff takes file paths and mypy resolves via mypy_path, so neither needs it.
VENV_PYTHON_SRC := PYTHONPATH=$(CURDIR)/src $(VENV_PYTHON)

.PHONY: install lock fmt lint type test test-all hooks build up up-build down ps logs clean bootstrap dbt-build dbt-docs

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

ps:  ## Show stack status
	docker compose ps

logs:  ## Tail stack logs
	docker compose logs -f --tail=100

clean:  ## Remove caches
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
	find . -type d -name __pycache__ -not -path "./node_modules/*" -exec rm -rf {} +

# Repeated `make build` accumulates BuildKit layer cache without bound — 20 GB over ten
# days here. The uv wheel cache (type=exec.cachemount) is deliberately KEPT: it is what
# lets a rebuild survive a flaky connection by resuming downloads instead of restarting
# ~200 wheels, and it is ~1 GB against the ~19 GB of layer cache worth reclaiming.
backup:  ## Snapshot the market database (options history + live record are unbackfillable)
	./scripts/backup-market.sh

prune-cache:  ## Reclaim Docker build cache, keeping the uv wheel cache
	docker builder prune --force --filter "type!=exec.cachemount"
	docker image prune --force
	@docker system df
