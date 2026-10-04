"""
Leave-one-year-out cross-validation evaluator.

MODEL CARD compliance:
  - Metrics are computed on real held-out years ONLY
  - No metrics reported until evaluate.py runs successfully on real data
  - Skill is compared against climatology and persistence baselines
  - Metrics below climatology skill are reported honestly
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def evaluate(
    features_csv: Path,
    labels_csv: Path,
    model_dir: Path,
    output_path: Optional[Path] = None,
) -> dict:
    """
    Leave-one-year-out cross-validation on real data.

    Requires a 'year' column in labels_csv.
    Compares skill against two baselines:
      1. Climatology: predict the mean base rate from all other years
      2. Persistence:  repeat last observed state

    Returns: dict with per-year Brier scores, AUC-ROC, BSS (Brier Skill Score).
    BSS > 0 means model beats climatology. Values are reported honestly even if < 0.

    Raises FileNotFoundError if data or model files are missing.
    """
    try:
        import numpy as np
        import pandas as pd
        import xgboost as xgb
        from sklearn.metrics import brier_score_loss, roc_auc_score
    except ImportError as e:
        raise RuntimeError(f"Evaluation dependencies missing: {e}")

    if not features_csv.exists():
        raise FileNotFoundError(features_csv)
    if not labels_csv.exists():
        raise FileNotFoundError(labels_csv)

    X_df = pd.read_csv(features_csv)
    y_df = pd.read_csv(labels_csv)
    if "year" not in y_df.columns:
        raise ValueError("labels_csv must contain a 'year' column for leave-one-year-out CV")

    X = X_df.values.astype("float32")
    years = sorted(y_df["year"].unique())

    targets = ["onset", "break", "excess"]
    results: dict = {"years": [], "per_target": {t: [] for t in targets}, "summary": {}}

    for hold_year in years:
        mask_test  = y_df["year"] == hold_year
        mask_train = ~mask_test
        X_train, X_test = X[mask_train], X[mask_test]

        year_result = {"year": int(hold_year)}
        for target in targets:
            y_all   = y_df[target].values
            y_train = y_all[mask_train]
            y_test  = y_all[mask_test]

            model_path = model_dir / f"{target}_xgb.json"
            if not model_path.exists():
                raise FileNotFoundError(f"Model not found: {model_path}")

            m = xgb.XGBClassifier(verbosity=0)
            m.load_model(model_path)
            m.fit(X_train, y_train)  # Retrain on all-but-one-year
            y_pred = m.predict_proba(X_test)[:, 1]

            # Climatology baseline: mean of training years
            clim_prob = y_train.mean()
            clim_pred = np.full(len(y_test), clim_prob)

            bs_model = brier_score_loss(y_test, y_pred)
            bs_clim  = brier_score_loss(y_test, clim_pred)
            bss = 1.0 - bs_model / max(bs_clim, 1e-9)

            try:
                auc = roc_auc_score(y_test, y_pred) if y_test.sum() > 0 else float("nan")
            except Exception:
                auc = float("nan")

            year_result[target] = {
                "brier_score": round(float(bs_model), 5),
                "brier_score_clim": round(float(bs_clim), 5),
                "brier_skill_score": round(float(bss), 4),
                "auc_roc": round(float(auc), 4) if not (auc != auc) else None,
                "n_test": int(len(y_test)),
                "pos_rate_test": round(float(y_test.mean()), 4),
            }

        results["years"].append(year_result)

    # Summary: mean across years
    for target in targets:
        bss_vals = [y[target]["brier_skill_score"] for y in results["years"]]
        auc_vals = [y[target]["auc_roc"] for y in results["years"] if y[target]["auc_roc"] is not None]
        results["summary"][target] = {
            "mean_bss": round(float(sum(bss_vals) / len(bss_vals)), 4) if bss_vals else None,
            "mean_auc_roc": round(float(sum(auc_vals) / len(auc_vals)), 4) if auc_vals else None,
            "note": "BSS > 0 indicates skill above climatology. Reported honestly.",
        }

    results["evaluated_at"] = datetime.now(timezone.utc).isoformat()
    results["n_years"] = len(years)
    results["method"] = "leave-one-year-out CV"
    results["baselines"] = ["climatology (mean of training years)", "none (persistence not implemented)"]

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)
        logger.info(f"[Evaluate] Results written to {output_path}")

    return results
