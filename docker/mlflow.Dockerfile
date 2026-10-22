# Pinned to the version the Python client is locked to (pyproject/uv.lock) — `latest`
# means unreproducible builds and whatever upstream pushed. Bump alongside the client.
FROM ghcr.io/mlflow/mlflow:v3.17.1

# timeout/retries: pip's 15s default drops on slow laptop Wi-Fi (same as UV_HTTP_TIMEOUT)
RUN pip install --no-cache-dir --timeout 120 --retries 5 psycopg2-binary

EXPOSE 5000
# One worker keeps the footprint small. MLflow has no authentication, so its own host and origin
# checks are what keep a web page in this machine's browser out: binding to loopback stops the LAN,
# not the browser. Hosts are the in-network name (the pipeline, `mlflow:5000`), the healthcheck
# (`localhost:5000`) and the host port (`localhost`/`127.0.0.1:5001`); the only cross-origin caller
# allowed is MLflow's own UI. Never `*`: that let any website call the registry's write API.
CMD ["sh", "-c", "mlflow server --backend-store-uri \"$MLFLOW_BACKEND_URI\" --artifacts-destination /mlartifacts --host 0.0.0.0 --port 5000 --workers 1 --allowed-hosts 'mlflow,mlflow:5000,localhost,localhost:5000,localhost:5001,127.0.0.1,127.0.0.1:5000,127.0.0.1:5001' --cors-allowed-origins 'http://localhost:5001,http://127.0.0.1:5001'"]
