# Data dictionary — `market` database

Populated from M1 onward; columns finalized alongside the Alembic migrations.

| Table | Grain | Purpose |
|---|---|---|
| `universe` | ticker | Tradable universe with metadata (name, type stock/etf, active flag) |
| `prices` | (ticker, date) | Daily OHLCV bars, adjusted; source column (yfinance/stooq) |
| `features` | (ticker, date) | Engineered features used for training and scoring |
| `predictions` | (ticker, date, model_version) | Champion-model forward-return scores |
| `model_runs` | run id | Training/evaluation/promotion audit log (metrics, decision, MLflow run id) |
| `drift_metrics` | (date, metric) | Evidently drift results per feature set |
| `portfolio_snapshots` | date | Simulated long/short book equity, exposure, turnover |
