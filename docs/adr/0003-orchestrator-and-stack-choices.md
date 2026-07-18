# ADR 0003: Dagster, React + FastAPI, and the zero-cost stack

**Status**: accepted · **Date**: 2026-07-18

## Context

The platform needs scheduled/reactive orchestration, experiment tracking, serving, and a dashboard — all free, all local, comfortable on 16 GB RAM. The author uses Airflow 3.x professionally but is open to better-fitting tools.

## Decision

- **Dagster** over Airflow/Prefect: asset-based model fits ML lineage (prices → features → model → predictions), daily partitions + backfills match market data, asset checks give data quality for free, and the footprint (~1–1.5 GB) is roughly half of Airflow's. Orchestration concepts still transfer to Airflow at work.
- **FastAPI + React (Vite, TypeScript)** rather than Streamlit: a real API/frontend split showcases full-stack skills and keeps the serving layer reusable.
- **MLflow** for tracking + registry; champion/challenger via registry aliases (`@champion`).
- **Postgres 17** as the single database server (app data, Dagster storage, MLflow backend) — one container, DBeaver-friendly.
- **uv + ruff + mypy + pytest + pre-commit** for modern, fast Python tooling; GitHub Actions (free on public repos) for CI.

## Consequences

One new tool to learn (Dagster) in exchange for a lighter stack and stronger ML ergonomics. The React app is more work than Streamlit; accepted for portfolio value.
