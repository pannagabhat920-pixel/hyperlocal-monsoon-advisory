"""
Deterministic monsoon forecast simulator.

PRIMARY forecast engine for Phase 3 (before XGBoost is trained on CHIRPS hindcast).
Uses sign-correct climatological priors adjusted by current ENSO/IOD/MJO state.

DATA HONESTY:
  - All output carries data_source=SIMULATED
  - MUST NEVER reach a real messaging provider (enforced by BLOCKED_SIMULATED)
  - No skill metrics are produced here — this is not a scored model
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Optional

# ─── Climatological priors (India, June–September monsoon) ───────────────────
_CLIM_ONSET  = {1: 0.55, 2: 0.48, 3: 0.40, 4: 0.33}
_CLIM_BREAK  = {1: 0.18, 2: 0.22, 3: 0.25, 4: 0.28}
_CLIM_EXCESS = {1: 0.25, 2: 0.22, 3: 0.20, 4: 0.18}
_CLIM_CONF   = {1: 0.72, 2: 0.60, 3: 0.48, 4: 0.35}
_CLIM_P50    = {1: 42.0, 2: 38.0, 3: 35.0, 4: 32.0}  # mm per 7-day window


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _enso_adj(nino34: float) -> dict[str, float]:
    """
    El Niño (nino34 > 0.5): weaker Indian monsoon → lower onset, higher break.
    La Niña (nino34 < -0.5): stronger monsoon → higher onset, lower break.
    """
    if nino34 > 1.5:
        return {"onset": -0.15, "break": +0.12, "excess": -0.08, "rain": -0.20}
    elif nino34 > 0.5:
        return {"onset": -0.08, "break": +0.06, "excess": -0.04, "rain": -0.10}
    elif nino34 < -1.5:
        return {"onset": +0.15, "break": -0.10, "excess": +0.10, "rain": +0.22}
    elif nino34 < -0.5:
        return {"onset": +0.08, "break": -0.05, "excess": +0.06, "rain": +0.12}
    return {"onset": 0.0, "break": 0.0, "excess": 0.0, "rain": 0.0}


def _iod_adj(dmi: float) -> dict[str, float]:
    """
    Positive IOD (dmi > 0.4): suppressed Indian rainfall.
    Negative IOD (dmi < -0.4): enhanced Indian rainfall.
    """
    if dmi > 0.8:
        return {"onset": -0.08, "break": +0.08, "excess": -0.06, "rain": -0.12}
    elif dmi > 0.4:
        return {"onset": -0.04, "break": +0.04, "excess": -0.03, "rain": -0.06}
    elif dmi < -0.8:
        return {"onset": +0.06, "break": -0.06, "excess": +0.05, "rain": +0.10}
    elif dmi < -0.4:
        return {"onset": +0.03, "break": -0.03, "excess": +0.02, "rain": +0.05}
    return {"onset": 0.0, "break": 0.0, "excess": 0.0, "rain": 0.0}


def _mjo_adj(phase: int, amplitude: float) -> dict[str, float]:
    """
    MJO phases 2-3 (Indian Ocean): enhance monsoon onset.
    MJO phases 6-7 (western Pacific): suppress Indian monsoon.
    Weak MJO (amplitude < 1.0): no adjustment.
    """
    if amplitude < 1.0:
        return {"onset": 0.0, "break": 0.0, "excess": 0.0, "rain": 0.0}
    f = min(amplitude / 2.0, 1.0)
    if phase in (2, 3):
        return {"onset": +0.10*f, "break": -0.08*f, "excess": +0.08*f, "rain": +0.15*f}
    if phase == 4:
        return {"onset": +0.05*f, "break": -0.04*f, "excess": +0.04*f, "rain": +0.08*f}
    if phase in (6, 7):
        return {"onset": -0.10*f, "break": +0.08*f, "excess": -0.07*f, "rain": -0.12*f}
    return {"onset": 0.0, "break": 0.0, "excess": 0.0, "rain": 0.0}


def _lat_adj(lat: float) -> dict[str, float]:
    """
    Monsoon advances northward: Kerala (8°N) onset June 1, Punjab (31°N) onset July 5.
    """
    delta = (lat - 19.5) / 12.0  # ~0 at centre of India
    return {"onset": -0.15 * delta, "break": 0.0, "excess": 0.0, "rain": 0.0}


def simulate_forecast(
    panchayat_id: int,
    lat: float,
    lon: float,
    lead_week: int,
    nino34: float = 0.0,
    iod_dmi: float = 0.0,
    mjo_phase: int = 3,
    mjo_amplitude: float = 1.0,
    issue_date: Optional[date] = None,
    open_meteo_weekly: Optional[dict] = None,
) -> dict:
    """
    Produce a SIMULATED forecast for one panchayat at one lead week.

    If open_meteo_weekly is provided (live NWP), blends it with climatology
    for rainfall percentiles. Probabilities are always SIMULATED.

    Returns dict matching GridForecast model fields.
    """
    if issue_date is None:
        issue_date = date.today()

    enso = _enso_adj(nino34)
    iod  = _iod_adj(iod_dmi)
    mjo  = _mjo_adj(mjo_phase, mjo_amplitude)
    loc  = _lat_adj(lat)

    def adj(key: str) -> float:
        return enso[key] + iod[key] + mjo[key] + loc.get(key, 0.0)

    onset_prob      = _clamp(_CLIM_ONSET.get(lead_week, 0.30)  + adj("onset"))
    break_prob      = _clamp(_CLIM_BREAK.get(lead_week, 0.25)  + adj("break"))
    excess_rain_prob = _clamp(_CLIM_EXCESS.get(lead_week, 0.20) + adj("excess"))
    confidence      = _clamp(_CLIM_CONF.get(lead_week, 0.35)   - (lead_week - 1) * 0.05)

    rain_factor = 1.0 + adj("rain")
    base_p50 = _CLIM_P50.get(lead_week, 30.0) * rain_factor

    if open_meteo_weekly and lead_week in open_meteo_weekly:
        nwp = open_meteo_weekly[lead_week]
        nwp_p50 = nwp.get("p50_rainfall_mm", base_p50)
        nwp_p10 = nwp.get("p10_rainfall_mm", nwp_p50 * 0.5)
        nwp_p90 = nwp.get("p90_rainfall_mm", nwp_p50 * 1.6)
        # Blend: 60% NWP + 40% climatology (less weight on NWP for weeks 3-4)
        nwp_weight = 0.6 if lead_week <= 2 else 0.3
        clim_weight = 1.0 - nwp_weight
        p50 = nwp_weight * nwp_p50 + clim_weight * base_p50
        p10 = nwp_weight * nwp_p10 + clim_weight * base_p50 * 0.5
        p90 = nwp_weight * nwp_p90 + clim_weight * base_p50 * 1.6
    else:
        p50 = base_p50
        p10 = p50 * 0.50
        p90 = p50 * 1.60

    target_week_start = issue_date + timedelta(weeks=lead_week - 1)
    target_week_end   = target_week_start + timedelta(days=6)

    return {
        "panchayat_id":      panchayat_id,
        "issue_date":        issue_date,
        "target_week_start": target_week_start,
        "target_week_end":   target_week_end,
        "lead_week":         lead_week,
        "onset_prob":        round(onset_prob, 4),
        "break_prob":        round(break_prob, 4),
        "excess_rain_prob":  round(excess_rain_prob, 4),
        "p10_rainfall_mm":   round(max(0.0, p10), 1),
        "p50_rainfall_mm":   round(max(0.0, p50), 1),
        "p90_rainfall_mm":   round(max(0.0, p90), 1),
        "confidence":        round(confidence, 4),
        "data_source":       "SIMULATED",
        "features_json": {
            "nino34": nino34, "iod_dmi": iod_dmi,
            "mjo_phase": mjo_phase, "mjo_amplitude": mjo_amplitude,
            "lat": lat, "lon": lon, "lead_week": lead_week,
            "adjustments": {"enso": enso, "iod": iod, "mjo": mjo, "location": loc},
        },
        "shap_values_json": None,
    }
