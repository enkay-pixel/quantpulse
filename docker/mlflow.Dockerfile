# Pinned to the version the Python client is locked to (pyproject/uv.lock) — `latest`
# means unreproducible builds and whatever upstream pushed. Bump alongside the client.
FROM ghcr.io/mlflow/mlflow:v3.14.0

# timeout/retries: pip's 15s default drops on slow laptop Wi-Fi (same as UV_HTTP_TIMEOUT)
RUN pip install --no-cache-dir --timeout 120 --retries 5 psycopg2-binary

EXPOSE 5000
# One worker keeps the footprint small; allowed-hosts covers in-network access as `mlflow:5000`
CMD ["sh", "-c", "mlflow server --backend-store-uri \"$MLFLOW_BACKEND_URI\" --artifacts-destination /mlartifacts --host 0.0.0.0 --port 5000 --workers 1 --allowed-hosts '*' --cors-allowed-origins '*'"]
