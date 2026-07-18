# Shared image for dagster-webserver and dagster-daemon (single code location,
# loaded in-process from the installed package — no separate gRPC server needed).
FROM python:3.14-slim

# libgomp1: LightGBM runtime; curl: container healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/usr/local UV_COMPILE_BYTECODE=1
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project --no-dev

COPY src ./src
COPY alembic.ini ./
COPY alembic ./alembic
COPY configs ./configs
COPY docker/dagster.yaml docker/workspace.yaml /opt/dagster/
RUN uv sync --frozen --no-dev

ENV DAGSTER_HOME=/opt/dagster
EXPOSE 3000
