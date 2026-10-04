"""
ML model pipeline — XGBoost + ConvLSTM.

PIPELINE STATUS: UNTRAINED (Phase 3 — Option B from model card).
Training occurs after CHIRPS hindcast data is sourced.
Until trained, PannagaForecaster.predict() raises RuntimeError;
the simulator provides all SIMULATED forecasts.

No metrics are stored or reported for untrained models.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

import numpy as np

logger = logging.getLogger(__name__)

MODEL_DIR = Path(os.getenv("MODEL_DIR", "/app/model_weights"))


class XGBoostForecaster:
    """
    Three-head XGBoost ensemble for onset, break, and excess-rain probabilities.
    Status: pipeline-only, untrained.
    """

    def __init__(self):
        self.onset_model = None
        self.break_model = None
        self.excess_model = None
        self.is_trained = False
        self.version_tag: Optional[str] = None

    def load(self, model_dir: Path = MODEL_DIR) -> bool:
        """Load saved models from disk. Returns True if all three found."""
        try:
            import xgboost as xgb
            paths = {
                "onset":  model_dir / "onset_xgb.json",
                "break":  model_dir / "break_xgb.json",
                "excess": model_dir / "excess_xgb.json",
            }
            if not all(p.exists() for p in paths.values()):
                logger.info("[XGBoost] Model files not found — untrained pipeline")
                return False
            self.onset_model  = xgb.XGBClassifier(); self.onset_model.load_model(paths["onset"])
            self.break_model  = xgb.XGBClassifier(); self.break_model.load_model(paths["break"])
            self.excess_model = xgb.XGBClassifier(); self.excess_model.load_model(paths["excess"])
            self.is_trained = True
            logger.info("[XGBoost] Models loaded from disk")
            return True
        except ImportError:
            logger.warning("[XGBoost] xgboost not installed")
            return False

    def predict(self, X: np.ndarray) -> dict[str, np.ndarray]:
        if not self.is_trained:
            raise RuntimeError(
                "XGBoostForecaster is untrained. Use simulator.simulate_forecast() instead."
            )
        return {
            "onset_prob":       self.onset_model.predict_proba(X)[:, 1],
            "break_prob":       self.break_model.predict_proba(X)[:, 1],
            "excess_rain_prob": self.excess_model.predict_proba(X)[:, 1],
        }

    def save(self, model_dir: Path = MODEL_DIR) -> None:
        if not self.is_trained:
            raise RuntimeError("Cannot save untrained model")
        model_dir.mkdir(parents=True, exist_ok=True)
        self.onset_model.save_model(model_dir / "onset_xgb.json")
        self.break_model.save_model(model_dir / "break_xgb.json")
        self.excess_model.save_model(model_dir / "excess_xgb.json")


class ConvLSTMForecaster:
    """
    Spatial ConvLSTM for block-level grid propagation.

    Architecture:
      Input : (T, B, C, H, W) sequence of block feature grids
      Layers: 2× ConvLSTMCell, 64 hidden dims, 3×3 kernel
      Output: (B, 3, H, W) — onset, break, excess probabilities per cell

    Status: architecture-only, untrained. Requires torch (CPU-only in Docker).
    """

    def __init__(self):
        self.model = None
        self.is_trained = False

    def build(self, in_channels: int = 14, hidden_dim: int = 64) -> bool:
        """Build the PyTorch model graph. Returns True if torch is available."""
        try:
            import torch
            import torch.nn as nn

            class ConvLSTMCell(nn.Module):
                def __init__(self, in_ch, hidden, kernel=3):
                    super().__init__()
                    pad = kernel // 2
                    self.conv = nn.Conv2d(in_ch + hidden, 4 * hidden, kernel, padding=pad)
                    self.hidden = hidden

                def forward(self, x, h, c):
                    i, f, g, o = torch.chunk(self.conv(torch.cat([x, h], 1)), 4, 1)
                    c_new = torch.sigmoid(f) * c + torch.sigmoid(i) * torch.tanh(g)
                    h_new = torch.sigmoid(o) * torch.tanh(c_new)
                    return h_new, c_new

            class SpatialModel(nn.Module):
                def __init__(self, in_ch, hidden):
                    super().__init__()
                    self.l1 = ConvLSTMCell(in_ch, hidden)
                    self.l2 = ConvLSTMCell(hidden, hidden)
                    self.head = nn.Sequential(nn.Conv2d(hidden, 3, 1), nn.Sigmoid())

                def forward(self, seq):  # seq: (T, B, C, H, W)
                    T, B, _, H, W = seq.shape
                    h1 = c1 = torch.zeros(B, self.l1.hidden, H, W)
                    h2 = c2 = torch.zeros(B, self.l2.hidden, H, W)
                    for t in range(T):
                        h1, c1 = self.l1(seq[t], h1, c1)
                        h2, c2 = self.l2(h1, h2, c2)
                    return self.head(h2)  # (B, 3, H, W)

            self.model = SpatialModel(in_channels, hidden_dim)
            self.model.eval()
            logger.info(f"[ConvLSTM] Graph built: in_ch={in_channels} hidden={hidden_dim}")
            return True
        except ImportError:
            logger.warning("[ConvLSTM] torch not available — skipping")
            return False

    def predict(self, x_seq: Any) -> Any:
        if not self.is_trained:
            raise RuntimeError("ConvLSTMForecaster is untrained.")
        import torch
        with torch.no_grad():
            return self.model(x_seq)


# ─── Module-level singletons (lazily loaded) ─────────────────────────────────

_xgb: Optional[XGBoostForecaster] = None
_convlstm: Optional[ConvLSTMForecaster] = None


def get_xgb_forecaster() -> XGBoostForecaster:
    global _xgb
    if _xgb is None:
        _xgb = XGBoostForecaster()
        _xgb.load()
    return _xgb


def get_convlstm_forecaster() -> ConvLSTMForecaster:
    global _convlstm
    if _convlstm is None:
        _convlstm = ConvLSTMForecaster()
        _convlstm.build()
    return _convlstm
