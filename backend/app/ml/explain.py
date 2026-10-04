"""
SHAP explanation module.

Phase 3 status: returns None for all untrained models (no fabricated importances).
When XGBoost is trained (Phase 8+), this produces TreeExplainer SHAP values
with feature names from feature_builder.FEATURE_NAMES.
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np

from app.ml.feature_builder import FEATURE_NAMES

logger = logging.getLogger(__name__)


def explain(
    model,
    X: np.ndarray,
    max_samples: int = 100,
) -> Optional[dict]:
    """
    Compute SHAP values for feature matrix X using TreeExplainer.

    Returns None if model is untrained or shap is unavailable.
    Returns dict: {"feature_names": [...], "values": [[...], ...]} for top features.
    """
    if model is None or not getattr(model, "is_trained", False):
        logger.debug("[SHAP] Skipping — model untrained")
        return None

    try:
        import shap

        # Sample for speed
        if len(X) > max_samples:
            idx = np.random.choice(len(X), max_samples, replace=False)
            X_sample = X[idx]
        else:
            X_sample = X

        explainer = shap.TreeExplainer(model.onset_model)  # type: ignore
        shap_values = explainer.shap_values(X_sample)

        mean_abs = np.abs(shap_values).mean(axis=0)
        top_idx = np.argsort(mean_abs)[::-1][:10]

        return {
            "feature_names": [FEATURE_NAMES[i] for i in top_idx],
            "mean_abs_shap":  mean_abs[top_idx].tolist(),
            "n_samples":      len(X_sample),
        }
    except ImportError:
        logger.warning("[SHAP] shap package not installed — skipping explanations")
        return None
    except Exception as e:
        logger.warning(f"[SHAP] explain failed: {e}")
        return None


def explain_single(
    model,
    x: np.ndarray,
) -> Optional[dict]:
    """
    Compute SHAP values for a single feature vector x of shape (N_FEATURES,).

    Returns dict: {"feature_contributions": {"feature_name": shap_value, ...}}
    or None if unavailable.
    """
    if model is None or not getattr(model, "is_trained", False):
        return None
    try:
        import shap
        explainer = shap.TreeExplainer(model.onset_model)  # type: ignore
        sv = explainer.shap_values(x.reshape(1, -1))[0]
        return {
            "feature_contributions": {
                FEATURE_NAMES[i]: round(float(sv[i]), 5)
                for i in range(len(FEATURE_NAMES))
            }
        }
    except Exception as e:
        logger.debug(f"[SHAP] explain_single failed: {e}")
        return None
