FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

# Pinned to the uv that wrote uv.lock; `latest` made builds unreproducible.
COPY --from=ghcr.io/astral-sh/uv:0.11.29 /uv /usr/local/bin/uv

WORKDIR /app
# UV_HTTP_TIMEOUT: default 30s drops large wheels (scipy ~35MB) on slow laptop Wi-Fi.
# The cache mount keeps downloaded wheels across builds, so a flaky network makes
# incremental progress instead of restarting ~200 downloads per attempt.
ENV UV_PROJECT_ENVIRONMENT=/usr/local UV_COMPILE_BYTECODE=1 UV_HTTP_TIMEOUT=300 \
    UV_LINK_MODE=copy UV_CONCURRENT_DOWNLOADS=8
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-install-project --no-dev

COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev

EXPOSE 8000
CMD ["uvicorn", "quantpulse.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
