FROM ghcr.io/mlflow/mlflow:latest

RUN pip install --no-cache-dir psycopg2-binary

EXPOSE 5000
# One worker keeps the footprint small; allowed-hosts covers in-network access as `mlflow:5000`
CMD ["sh", "-c", "mlflow server --backend-store-uri \"$MLFLOW_BACKEND_URI\" --artifacts-destination /mlartifacts --host 0.0.0.0 --port 5000 --workers 1 --allowed-hosts '*' --cors-allowed-origins '*'"]
