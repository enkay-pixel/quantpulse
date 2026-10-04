"""Fit the fixed-default configuration beside the weekly candidate, for comparison only.

The fixed-defaults study found a fixed configuration no worse than the tuned one on XJSE and
better on XNYS, on holdouts that had been consulted many times before. A shadow run gathers the
evidence that study cannot: the same comparison, made every week on data that did not exist when
the decision to look was taken.

What makes it safe to run inside the production retrain is what it does *not* do:

  * It is never registered, so no alias can point at it and nothing can deserialize it as a
    champion. It does not touch MLflow at all.
  * It is never gated. It sits the same exam as the candidate — the same panel, the same holdout,
    the same seed — but nothing reads its result to make a decision.
  * It cannot be recorded as a promotion. Its rows carry their own run type, which every reader
    that selects `run_type = 'train'` already passes over, and the table refuses a shadow with any
    decision at all, because several readers identify champions by the decision alone.
  * It runs after the production candidate has committed, in a session of its own, so a shadow
    that fails — or that the table refuses — cannot roll back the production row it accompanies.

Its result is only useful paired with that production row, and pairing is checked rather than
assumed: if the two did not sit the same holdout, the row says so.
"""

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from quantpulse.data.calendar import get_exchange
from quantpulse.db import ModelRun
from quantpulse.features.engineering import feature_columns_for
from quantpulse.ml.fixed_defaults import fixed_default
from quantpulse.ml.training import HOLDOUT_FRACTION, TrainConfig, split_by_date, train_final_model

logger = logging.getLogger(__name__)

#: The configuration under trial. The fixed-defaults study pre-registered this one as the only
#: candidate for adoption, so it is the only one worth carrying into production conditions.
SHADOW_ARM = "fixed_default"

#: Fields that define which exam a model sat. A shadow is only comparable with the production
#: candidate if every one of them matches.
PAIRING_FIELDS = ("holdout_start", "holdout_end", "holdout_days", "train_start", "train_end")


def record_shadow(
    engine: Engine,
    session: Session,
    exchange: str,
    cfg: TrainConfig | None = None,
) -> dict[str, object]:
    """Fit the shadow configuration on this retrain's panel and record it beside the candidate.

    Called after the production candidate's row has committed. Reads that row to pair with it, and
    writes one `shadow` row. Never registers, gates or promotes anything.
    """
    from quantpulse.ml.pipeline import build_dataset, score_holdout

    cfg = cfg or TrainConfig()
    market = get_exchange(exchange)
    params = fixed_default(market.learning_rate_ceiling)

    frame = build_dataset(engine, cfg, exchange)
    feature_cols = feature_columns_for(exchange)
    train_frame, _ = split_by_date(frame, HOLDOUT_FRACTION, cfg.embargo_days)
    _, holdout = train_final_model(frame, feature_cols, params, cfg)
    metrics = score_holdout(holdout, market.quantile_width)
    window: dict[str, Any] = {
        "holdout_start": str(holdout["date"].min()),
        "holdout_end": str(holdout["date"].max()),
        "holdout_days": int(holdout["date"].nunique()),
        "train_start": str(train_frame["date"].min()),
        "train_end": str(train_frame["date"].max()),
    }

    production = session.scalars(
        select(ModelRun)
        .where(ModelRun.run_type == "train", ModelRun.exchange == exchange)
        .order_by(ModelRun.id.desc())
        .limit(1)
    ).first()
    paired = production is not None and all(
        production.metrics.get(k) == window[k] for k in PAIRING_FIELDS
    )
    if production is None:
        logger.warning("%s shadow found no production candidate to pair with", exchange)
    elif not paired:
        logger.warning(
            "%s shadow did not sit the same exam as candidate v%s — recorded, but not comparable",
            exchange,
            production.model_version,
        )

    production_ic = production.metrics.get("holdout_ic") if production is not None else None
    shadow_ic = metrics["holdout_ic"]
    comparison: dict[str, Any] = {
        "arm": SHADOW_ARM,
        "paired": paired,
        "shadows_version": production.model_version if production is not None else None,
        "shadows_run_id": production.id if production is not None else None,
        "production_holdout_ic": production_ic,
        # Only meaningful when paired; a difference between two different exams is not a result.
        "delta_ic": (shadow_ic - production_ic) if paired and production_ic is not None else None,
        "params": dict(params),
    }
    session.add(
        ModelRun(
            run_type="shadow",
            exchange=exchange,
            mlflow_run_id=None,
            model_version=None,
            metrics={**{k: v for k, v in metrics.items() if v == v}, **window, **comparison},
            decision=None,
        )
    )
    logger.info(
        "%s shadow (%s): holdout ic=%.4f against candidate v%s ic=%s%s",
        exchange,
        SHADOW_ARM,
        shadow_ic,
        comparison["shadows_version"],
        f"{production_ic:.4f}" if production_ic is not None else "n/a",
        "" if paired else " — NOT PAIRED",
    )
    return {
        "arm": SHADOW_ARM,
        "holdout_ic": round(shadow_ic, 6),
        "paired": paired,
        "shadows_version": comparison["shadows_version"],
        "delta_ic": round(comparison["delta_ic"], 6)
        if comparison["delta_ic"] is not None
        else None,
    }
