# ADR 0002: Consolidate two prototypes into one platform

**Status**: accepted · **Date**: 2026-07-18

## Context

Two earlier projects coexisted in the monorepo: `advanced_ml_investing` (a 519-line research monolith: features, purged CV, LightGBM, Transformer/GNN stubs, Optuna, backtester) and `mlops_investing` (a thin MLOps scaffold: MLflow logging, FastAPI stub, broken docker-compose, AWS/Terraform deploy). Both targeted the same idea and used outdated APIs (LightGBM 3.x callbacks, unmaintained `empyrical`, deprecated Optuna samplers).

## Decision

Replace both with QuantPulse, a single project built to production standards. Salvage the *logic* (feature definitions, purged/embargoed CV, backtester design), rewrite against current APIs. Delete the old folders; the monorepo commit `3d7d33e` preserves them.

Dropped from v1 (revisit later): PyTorch Transformer sequence model, GNN stub, ensemble stacking — they add ~2 GB of dependencies and materially complicate training on a 16 GB machine before the platform itself exists. All cloud deployment (Terraform/ECS) is out: the project has a **zero-cost constraint** and targets local Docker.

## Consequences

One codebase to test, document, and showcase. Research ideas that were stubs are now tracked as explicit future work instead of dead code.
