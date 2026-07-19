select
    id,
    run_type,
    mlflow_run_id,
    model_version,
    metrics,
    decision,
    created_at
from {{ source('market', 'model_runs') }}
