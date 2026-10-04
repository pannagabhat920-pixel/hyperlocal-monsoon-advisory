"""
Calibration module: isotonic regression to align simulator probabilities
with observed climatological base rates.

Phase 3 status: pipeline-only. Calibration fits only when hindcast
ground-truth labels are available (Phase 8+).
"""
from __future__ import annotations

import logging
import pickle
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

CALIBRATION_DIR = Path(__file__).parent.parent.parent / "model_weights" / "calibration"


class IsotonicCalibrator:
    """
    Per-target isotonic regression calibrator.
    Wraps sklearn's IsotonicRegression for P(onset), P(break), P(excess).
    """

    def __init__(self):
        self.onset_cal  = None
        self.break_cal  = None
        self.excess_cal = None
        self.is_fitted   = False

    def fit(
        self,
        raw_probs: dict[str, np.ndarray],
        labels:    dict[str, np.ndarray],
    ) -> None:
        """Fit calibrators from raw model probabilities and binary labels."""
        try:
            from sklearn.isotonic import IsotonicRegression
            self.onset_cal  = IsotonicRegression(out_of_bounds="clip")
            self.break_cal  = IsotonicRegression(out_of_bounds="clip")
            self.excess_cal = IsotonicRegression(out_of_bounds="clip")
            self.onset_cal.fit(raw_probs["onset_prob"],   labels["onset"])
            self.break_cal.fit(raw_probs["break_prob"],   labels["break"])
            self.excess_cal.fit(raw_probs["excess_rain_prob"], labels["excess"])
            self.is_fitted = True
            logger.info("[Calibration] Isotonic calibrators fitted")
        except ImportError:
            logger.warning("[Calibration] sklearn not available — skipping")

    def calibrate(
        self,
        raw_probs: dict[str, np.ndarray],
    ) -> dict[str, np.ndarray]:
        """Apply calibration. Returns raw probabilities if not fitted."""
        if not self.is_fitted:
            return raw_probs
        return {
            "onset_prob":       self.onset_cal.predict(raw_probs["onset_prob"]),
            "break_prob":       self.break_cal.predict(raw_probs["break_prob"]),
            "excess_rain_prob": self.excess_cal.predict(raw_probs["excess_rain_prob"]),
        }

    def save(self, path: Path = CALIBRATION_DIR) -> None:
        if not self.is_fitted:
            raise RuntimeError("Cannot save unfitted calibrator")
        path.mkdir(parents=True, exist_ok=True)
        with open(path / "isotonic_calibrators.pkl", "wb") as f:
            pickle.dump({"onset": self.onset_cal, "break": self.break_cal,
                         "excess": self.excess_cal}, f)

    def load(self, path: Path = CALIBRATION_DIR) -> bool:
        cal_path = path / "isotonic_calibrators.pkl"
        if not cal_path.exists():
            return False
        try:
            with open(cal_path, "rb") as f:
                d = pickle.load(f)
            self.onset_cal  = d["onset"]
            self.break_cal  = d["break"]
            self.excess_cal = d["excess"]
            self.is_fitted = True
            return True
        except Exception as e:
            logger.warning(f"[Calibration] Load failed: {e}")
            return False
