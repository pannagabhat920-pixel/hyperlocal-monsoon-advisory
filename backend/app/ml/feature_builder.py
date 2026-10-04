"""
Feature engineering for the Pannaga ML pipeline.

FEATURE_NAMES defines the column order — must stay stable across train/eval/predict.
"""
from __future__ import annotations

import math
from datetime import date
from typing import Optional

import numpy as np

FEATURE_NAMES = [
    "nino34",            # ENSO Niño3.4 anomaly (°C)
    "iod_dmi",           # Indian Ocean Dipole Mode Index (°C)
    "mjo_phase_sin",     # MJO phase encoded cyclically
    "mjo_phase_cos",
    "mjo_amplitude",     # MJO amplitude
    "lat",               # Panchayat latitude
    "lon",               # Panchayat longitude
    "lat_scaled",        # Normalised latitude (0=Kerala 8°N, 1=J&K 35°N)
    "lead_week",         # Forecast lead (1–4)
    "month",             # Issue month (1–12)
    "month_sin",         # Month encoded cyclically
    "month_cos",
    "onset_climatology", # Climatological onset probability for (lat, month)
    "is_active_monsoon", # 1 if June–September
]

N_FEATURES = len(FEATURE_NAMES)


def _mjo_encode(phase: int) -> tuple[float, float]:
    angle = (phase - 1) * 2 * math.pi / 8
    return math.sin(angle), math.cos(angle)


def _month_encode(month: int) -> tuple[float, float]:
    angle = (month - 1) * 2 * math.pi / 12
    return math.sin(angle), math.cos(angle)


def _onset_climatology(lat: float, month: int) -> float:
    """Gaussian-shaped onset probability centred on the expected onset month."""
    if month < 5 or month > 9:
        return 0.05
    peak_month = 5.5 + (lat - 8.0) / 23.0 * 1.5
    dist = abs(month - peak_month)
    return max(0.05, 0.80 * math.exp(-0.5 * dist ** 2))


def build_features(
    nino34: float,
    iod_dmi: float,
    mjo_phase: int,
    mjo_amplitude: float,
    lat: float,
    lon: float,
    lead_week: int,
    issue_date: Optional[date] = None,
) -> np.ndarray:
    """Build feature vector for one (panchayat, lead_week, issue_date) point."""
    if issue_date is None:
        issue_date = date.today()
    month = issue_date.month

    mjo_sin, mjo_cos = _mjo_encode(mjo_phase)
    month_sin, month_cos = _month_encode(month)
    lat_scaled = (lat - 8.0) / (35.0 - 8.0)
    onset_clim = _onset_climatology(lat, month)
    is_active = 1.0 if month in (6, 7, 8, 9) else 0.0

    return np.array([
        nino34, iod_dmi, mjo_sin, mjo_cos, mjo_amplitude,
        lat, lon, lat_scaled,
        float(lead_week), float(month), month_sin, month_cos,
        onset_clim, is_active,
    ], dtype=np.float32)


def build_feature_matrix(records: list[dict]) -> np.ndarray:
    """Build (N, N_FEATURES) matrix from list of record dicts."""
    if not records:
        return np.empty((0, N_FEATURES), dtype=np.float32)
    return np.stack([
        build_features(
            r["nino34"], r["iod_dmi"], r["mjo_phase"], r["mjo_amplitude"],
            r["lat"], r["lon"], r["lead_week"], r.get("issue_date"),
        )
        for r in records
    ])
