"""
Free, keyless climate index ingestors.

Sources (all open HTTP, no API key required):
  - ENSO/ONI : NOAA CPC  https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt
  - MJO RMM  : NOAA CPC  https://www.cpc.ncep.noaa.gov/products/precip/CWlink/daily_mjo_index/pentad/pentad.index.RMM.txt
  - IOD/DMI  : NOAA PSL  https://psl.noaa.gov/gcos_wgsp/Timeseries/Data/dmi.had.long.data
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

NOAA_ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
NOAA_MJO_URL = (
    "https://www.cpc.ncep.noaa.gov/products/precip/CWlink/"
    "daily_mjo_index/pentad/pentad.index.RMM.txt"
)
NOAA_DMI_URL = "https://psl.noaa.gov/gcos_wgsp/Timeseries/Data/dmi.had.long.data"

MONTH_MAP = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4,
    "MAY": 5, "JUN": 6, "JUL": 7, "AUG": 8,
    "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}

TIMEOUT = 30


def fetch_oni() -> Optional[dict]:
    """
    Fetch the latest ONI (Oceanic Niño Index / Nino3.4 anomaly) from NOAA CPC.

    File format (space-separated):
        SEAS  YR TOTAL  CLIM  ANOM  TOTAL CLIM  ANOM
        DJF 1950 24.26 26.51 -2.25 ...
    We take the ANOM from the last valid data row (col index 4).
    """
    try:
        resp = httpx.get(NOAA_ONI_URL, timeout=TIMEOUT, follow_redirects=True)
        resp.raise_for_status()
        latest = None
        for line in resp.text.strip().splitlines():
            parts = line.split()
            if len(parts) < 5:
                continue
            seas = parts[0].upper()
            # Season code is 3 chars like DJF, JFM, FMA …
            if len(seas) == 3 and seas[:3].upper() in {
                "DJF","JFM","FMA","MAM","AMJ","MJJ","JJA","JAS","ASO","SON","OND","NDJ"
            }:
                try:
                    year = int(parts[1])
                    anom = float(parts[4])
                    # Use first month of season as date
                    m1 = MONTH_MAP.get(seas[:3], MONTH_MAP.get(seas[0:3]))
                    month = m1 if m1 else 1
                    latest = {"date": date(year, month, 15), "nino34": anom}
                except (ValueError, IndexError):
                    continue
        if latest:
            logger.info(f"[ONI] nino34={latest['nino34']:.2f} at {latest['date']}")
        return latest
    except Exception as e:
        logger.warning(f"[ONI] Fetch failed: {e}")
        return None


def fetch_mjo() -> Optional[dict]:
    """
    Fetch latest MJO RMM phase and amplitude from NOAA CPC pentad file.

    File format (space-separated):
        YEAR MONTH DAY RMM1 RMM2 PHASE AMPLITUDE
    """
    try:
        resp = httpx.get(NOAA_MJO_URL, timeout=TIMEOUT, follow_redirects=True)
        resp.raise_for_status()
        latest = None
        for line in resp.text.strip().splitlines():
            parts = line.split()
            if len(parts) < 7:
                continue
            try:
                year = int(parts[0])
                month = int(parts[1])
                day = int(parts[2])
                phase = int(float(parts[5]))
                amplitude = float(parts[6])
                if 1 <= phase <= 8 and 1900 < year < 2100 and 1 <= month <= 12:
                    latest = {
                        "date": date(year, month, min(day, 28)),
                        "mjo_phase": phase,
                        "mjo_amplitude": round(amplitude, 3),
                    }
            except (ValueError, IndexError):
                continue
        if latest:
            logger.info(
                f"[MJO] phase={latest['mjo_phase']} amp={latest['mjo_amplitude']:.2f}"
                f" at {latest['date']}"
            )
        return latest
    except Exception as e:
        logger.warning(f"[MJO] Fetch failed: {e}")
        return None


def fetch_dmi() -> Optional[dict]:
    """
    Fetch latest IOD/DMI from NOAA PSL.

    File format: YEAR JAN FEB MAR … DEC (monthly, -999.9 = missing)
    """
    try:
        resp = httpx.get(NOAA_DMI_URL, timeout=TIMEOUT, follow_redirects=True)
        resp.raise_for_status()
        latest = None
        for line in resp.text.strip().splitlines():
            parts = line.split()
            if len(parts) < 2:
                continue
            try:
                year = int(float(parts[0]))
                if not (1900 < year < 2100):
                    continue
                for month_idx, val_str in enumerate(parts[1:13], start=1):
                    val = float(val_str)
                    if abs(val) < 90.0:  # Filter fill values (-999, 999)
                        latest = {
                            "date": date(year, month_idx, 15),
                            "iod_dmi": round(val, 3),
                        }
            except (ValueError, IndexError):
                continue
        if latest:
            logger.info(f"[DMI] iod_dmi={latest['iod_dmi']:.3f} at {latest['date']}")
        return latest
    except Exception as e:
        logger.warning(f"[DMI] Fetch failed: {e}")
        return None


def fetch_all_indices() -> dict:
    """
    Fetch all climate indices. Returns combined dict with latest available values.
    Gracefully falls back to neutral values (0.0) if any source is unavailable.
    """
    oni = fetch_oni()
    mjo = fetch_mjo()
    dmi = fetch_dmi()

    result = {
        "nino34": oni["nino34"] if oni else 0.0,
        "iod_dmi": dmi["iod_dmi"] if dmi else 0.0,
        "mjo_phase": mjo["mjo_phase"] if mjo else 3,
        "mjo_amplitude": mjo["mjo_amplitude"] if mjo else 1.0,
        "fetch_date": date.today(),
        "source_dates": {
            "oni": str(oni["date"]) if oni else None,
            "mjo": str(mjo["date"]) if mjo else None,
            "dmi": str(dmi["date"]) if dmi else None,
        },
        "all_live": all([oni, mjo, dmi]),
    }
    logger.info(
        f"[Indices] nino34={result['nino34']:.2f} dmi={result['iod_dmi']:.3f} "
        f"mjo_phase={result['mjo_phase']} all_live={result['all_live']}"
    )
    return result
