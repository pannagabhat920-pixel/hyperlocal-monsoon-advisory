"""
Spatial downscaler: interpolates block-level forecasts to panchayat level
using inverse-distance weighting and terrain adjustment.

Phase 3 status: functional (no training needed — purely spatial interpolation).
"""
from __future__ import annotations

import logging
import math
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def idw_interpolate(
    query_lat: float,
    query_lon: float,
    neighbors: list[dict],
    power: float = 2.0,
    min_dist_km: float = 0.1,
) -> dict:
    """
    Inverse-distance weighted interpolation.

    neighbors: list of dicts with keys:
        lat, lon, onset_prob, break_prob, excess_rain_prob,
        p10_rainfall_mm, p50_rainfall_mm, p90_rainfall_mm

    Returns interpolated probability dict.
    """
    if not neighbors:
        raise ValueError("At least one neighbor required for interpolation")
    if len(neighbors) == 1:
        return {k: v for k, v in neighbors[0].items() if k not in ("lat", "lon")}

    weights = []
    for n in neighbors:
        d = max(haversine_km(query_lat, query_lon, n["lat"], n["lon"]), min_dist_km)
        weights.append(1.0 / (d ** power))

    total_w = sum(weights)
    fields = ["onset_prob", "break_prob", "excess_rain_prob",
              "p10_rainfall_mm", "p50_rainfall_mm", "p90_rainfall_mm", "confidence"]

    result = {}
    for field in fields:
        vals = [n.get(field, 0.0) for n in neighbors]
        result[field] = sum(w * v for w, v in zip(weights, vals)) / total_w

    return result


def terrain_adjustment(
    p50_rainfall_mm: float,
    elevation_m: float,
    base_elevation_m: float = 400.0,
) -> float:
    """
    Orographic enhancement: +2.5% per 100 m above base elevation.
    Capped at 50% enhancement.
    """
    elev_diff = max(0.0, elevation_m - base_elevation_m)
    enhancement = 1.0 + min(0.50, elev_diff / 100.0 * 0.025)
    return round(p50_rainfall_mm * enhancement, 1)
