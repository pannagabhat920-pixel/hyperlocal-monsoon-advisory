"""
Open-Meteo free forecast API ingestor.

No API key required. Free tier: 16-day hourly/daily forecasts.
Docs: https://open-meteo.com/en/docs

For Weeks 3-4 (days 15-28) the free tier doesn't reach, so we
extrapolate using week 2 values with increasing uncertainty.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
FORECAST_DAYS = 16  # Free tier maximum
TIMEOUT = 30


def fetch_open_meteo(lat: float, lon: float) -> Optional[dict]:
    """
    Fetch daily precipitation/weather forecasts for a point (lat, lon).

    Returns dict keyed by lead_week (1-4) with weekly aggregates,
    or None on failure. Weeks 3-4 are extrapolated from week 2.
    """
    params = {
        "latitude": round(lat, 4),
        "longitude": round(lon, 4),
        "daily": [
            "precipitation_sum",
            "precipitation_probability_mean",
            "et0_fao_evapotranspiration",
            "temperature_2m_max",
            "temperature_2m_min",
            "weathercode",
        ],
        "timezone": "Asia/Kolkata",
        "forecast_days": FORECAST_DAYS,
    }
    try:
        resp = httpx.get(OPEN_METEO_URL, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if "daily" not in data:
            logger.warning(f"[OpenMeteo] No daily data for ({lat}, {lon})")
            return None

        daily = data["daily"]
        times = daily.get("time", [])
        precip = daily.get("precipitation_sum", [])
        precip_prob = daily.get("precipitation_probability_mean", [])

        # Aggregate days into weekly buckets
        weeks: dict[int, dict] = {}
        for i, t in enumerate(times):
            lw = i // 7 + 1  # lead_week 1..n
            if lw > 2:  # Only weeks 1-2 are from live data
                break
            if lw not in weeks:
                weeks[lw] = {"precip_mm": [], "precip_prob": [], "start_date": t}
            weeks[lw]["end_date"] = t
            if i < len(precip) and precip[i] is not None:
                weeks[lw]["precip_mm"].append(precip[i])
            if i < len(precip_prob) and precip_prob[i] is not None:
                weeks[lw]["precip_prob"].append(precip_prob[i])

        def _weekly_stats(vals: list, prob: list) -> dict:
            if not vals:
                return {}
            s = sorted(vals)
            n = len(s)
            total = sum(vals)
            p10 = s[max(0, int(0.1 * n))] * 7
            p50 = s[max(0, int(0.5 * n))] * 7
            p90 = s[max(0, int(0.9 * n))] * 7
            avg_prob = sum(prob) / max(len(prob), 1) / 100.0
            return {
                "p10_rainfall_mm": round(p10, 1),
                "p50_rainfall_mm": round(p50, 1),
                "p90_rainfall_mm": round(p90, 1),
                "weekly_total_mm": round(total, 1),
                "precip_probability": round(avg_prob, 3),
            }

        result = {}
        for lw, w in weeks.items():
            stats = _weekly_stats(w["precip_mm"], w.get("precip_prob", []))
            if stats:
                result[lw] = {
                    "lead_week": lw,
                    "target_week_start": w["start_date"],
                    "target_week_end": w.get("end_date", w["start_date"]),
                    "source": "LIVE",
                    **stats,
                }

        # Extrapolate weeks 3-4 from week 2 with increasing spread (uncertainty)
        if 2 in result:
            w2 = result[2]
            for lw in (3, 4):
                spread_factor = 1.0 + 0.3 * (lw - 2)  # increase spread
                decay = 0.90 ** (lw - 2)               # slight precipitation decay
                result[lw] = {
                    "lead_week": lw,
                    "target_week_start": w2["target_week_start"],
                    "target_week_end": w2["target_week_end"],
                    "source": "EXTRAPOLATED",
                    "p10_rainfall_mm": round(w2["p10_rainfall_mm"] * decay * 0.8, 1),
                    "p50_rainfall_mm": round(w2["p50_rainfall_mm"] * decay, 1),
                    "p90_rainfall_mm": round(w2["p90_rainfall_mm"] * decay * spread_factor, 1),
                    "weekly_total_mm": round(w2["weekly_total_mm"] * decay, 1),
                    "precip_probability": round(w2["precip_probability"] * decay, 3),
                }

        logger.info(f"[OpenMeteo] ({lat:.2f},{lon:.2f}) → {len(result)} weekly buckets")
        return result

    except Exception as e:
        logger.warning(f"[OpenMeteo] Fetch failed for ({lat},{lon}): {e}")
        return None
