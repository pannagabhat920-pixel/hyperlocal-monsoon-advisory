"""
Training pipeline for Phase 8+.

Phase 3 status: NOT runnable without CHIRPS hindcast data.
This module defines the training workflow so the architecture is ready.

MODEL CARD compliance:
  - Metrics are computed only on real held-out years (leave-one-year-out CV)
  - No metrics are written to the DB until evaluate.py completes successfully
  - The pipeline is documented in docs/model_card.md
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def train(
    features_csv: Path,
    labels_csv: Path,
    output_dir: Path,
    model_tag: str = "v1.0.0",
) -> dict:
    """
    Train XGBoost models for onset, break, and excess-rain prediction.

    Inputs:
      features_csv : path to (N, F) feature matrix CSV with column names
      labels_csv   : path to (N, 3) label CSV (onset, break, excess as 0/1)
      output_dir   : where to save model files and metrics JSON
      model_tag    : semantic version tag for model_versions table

    Returns: dict with training summary (no metrics — use evaluate.py)

    Raises FileNotFoundError if data files are missing.
    """
    try:
        import numpy as np
        import pandas as pd
        import xgboost as xgb
    except ImportError as e:
        raise RuntimeError(f"Training dependencies missing: {e}. Install with: uv pip install -e '.[ml]'")

    if not features_csv.exists():
        raise FileNotFoundError(f"Features file not found: {features_csv}")
    if not labels_csv.exists():
        raise FileNotFoundError(f"Labels file not found: {labels_csv}")

    logger.info(f"[Train] Loading data: features={features_csv} labels={labels_csv}")

    X = pd.read_csv(features_csv).values.astype("float32")
    y_df = pd.read_csv(labels_csv)

    targets = {
        "onset":  y_df["onset"].values,
        "break":  y_df["break"].values,
        "excess": y_df["excess"].values,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    models = {}

    for target_name, y in targets.items():
        logger.info(f"[Train] Training {target_name} model (N={len(X)}, pos_rate={y.mean():.3f})")
        model = xgb.XGBClassifier(
            n_estimators=200,
            max_depth=5,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            scale_pos_weight=(1 - y.mean()) / max(y.mean(), 0.01),
            random_state=42,
            eval_metric="logloss",
            verbosity=0,
        )
        model.fit(X, y)
        model_path = output_dir / f"{target_name}_xgb.json"
        model.save_model(model_path)
        models[target_name] = model
        logger.info(f"[Train] {target_name} model saved to {model_path}")

    summary = {
        "model_tag": model_tag,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "n_samples": len(X),
        "n_features": X.shape[1],
        "targets": list(targets.keys()),
        "note": "Run evaluate.py for skill metrics before reporting any scores.",
    }

    with open(output_dir / "training_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    logger.info(f"[Train] Complete. Run evaluate.py to compute skill metrics.")
    return summary
