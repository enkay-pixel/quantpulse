select
    id,
    run_type,
    exchange,
    mlflow_run_id,
    model_version,
    decision,
    metrics,
    created_at
from {{ source('market', 'model_runs') }}
