-- Runs once on first startup of the postgres volume.
-- The default database (market) holds app data: prices, features, predictions, portfolio.
-- dagster: Dagster run/event storage.  mlflow: MLflow tracking backend store.
CREATE DATABASE dagster;
CREATE DATABASE mlflow;
