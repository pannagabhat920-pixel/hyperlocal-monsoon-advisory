"""
Forecasts API Router.

Provides:
  - 4-week probabilistic outlook by Gram Panchayat (weeks 1-4)
  - Block-level forecast aggregations
  - SHAP explanation feature contributions
  - Data source honesty tags (LIVE | HINDCAST | SIMULATED)
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.climate import GridForecast
from app.models.geography import Block, District, Panchayat, State

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/forecasts", tags=["Forecasts"])


@router.get("/panchayat/{panchayat_id}", summary="4-week probabilistic outlook for Panchayat")
async def get_panchayat_forecast(
    panchayat_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Returns weeks 1, 2, 3, 4 probabilistic outlook for a Gram Panchayat.
    Includes percentiles (p10, p50, p90), SHAP values, and data_source banner flag.
    """
    # Verify panchayat exists
    p_result = await db.execute(
        select(Panchayat, Block, District, State)
        .join(Block, Panchayat.block_id == Block.id)
        .join(District, Block.district_id == District.id)
        .join(State, District.state_id == State.id)
        .where(Panchayat.id == panchayat_id)
    )
    p_row = p_result.first()
    if not p_row:
        raise HTTPException(status_code=404, detail="Gram Panchayat not found")

    panchayat, block, district, state = p_row

    # Fetch latest forecasts for weeks 1 to 4
    fc_result = await db.execute(
        select(GridForecast)
        .where(GridForecast.panchayat_id == panchayat_id)
        .order_by(GridForecast.issue_date.desc(), GridForecast.lead_week.asc())
        .limit(4)
    )
    forecasts = fc_result.scalars().all()

    # Sort by lead_week
    forecasts = sorted(forecasts, key=lambda f: f.lead_week)

    items = []
    has_simulated = False
    for fc in forecasts:
        if fc.data_source.value == "SIMULATED":
            has_simulated = True
        items.append({
            "id": fc.id,
            "lead_week": fc.lead_week,
            "target_week_start": fc.target_week_start.isoformat(),
            "target_week_end": fc.target_week_end.isoformat(),
            "onset_prob": fc.onset_prob,
            "break_prob": fc.break_prob,
            "excess_rain_prob": fc.excess_rain_prob,
            "false_onset_prob": getattr(fc, "false_onset_prob", 0.20),
            "break_duration_days_p50": getattr(fc, "break_duration_days_p50", 7.0),
            "p10_rainfall_mm": fc.p10_rainfall_mm,
            "p50_rainfall_mm": fc.p50_rainfall_mm,
            "p90_rainfall_mm": fc.p90_rainfall_mm,
            "confidence": fc.confidence,
            "data_source": fc.data_source.value,
            "shap_values": fc.shap_values_json,
            "features": fc.features_json,
        })

    return {
        "panchayat": {
            "id": panchayat.id,
            "name": panchayat.name,
            "block_name": block.name,
            "district_name": district.name,
            "state_name": state.name,
        },
        "forecasts": items,
        "simulated_banner": has_simulated,
        "is_live_outlook": not has_simulated,
    }
