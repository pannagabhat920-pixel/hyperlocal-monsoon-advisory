"""
GET /api/v1/advisories - List advisories for the authenticated farmer's panchayat.
GET /api/v1/advisories/{id} - Detail with translation.
GET /api/v1/advisories/{id}/translate/{lang} - On-demand translation.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user, require_role
from app.db.session import get_db
from app.models.agronomy import GeneratedAdvisory
from app.models.enums import AdvisoryApprovalStatus, UserRole
from app.models.users import FarmerProfile, User
from app.services.translation import SUPPORTED_LANGUAGES, translate_advisory

router = APIRouter(prefix="/advisories", tags=["Advisories"])


@router.get("", summary="List advisories for the current farmer's panchayat")
async def list_advisories(
    lead_week: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns APPROVED advisories for the farmer's panchayat (most recent first).
    Includes a persistent `simulated_banner` flag when data_source=SIMULATED.
    """
    # Determine farmer's panchayat
    profile_result = await db.execute(
        select(FarmerProfile).where(FarmerProfile.user_id == current_user.id)
    )
    profile = profile_result.scalar_one_or_none()

    if not profile or not profile.panchayat_id:
        return {"advisories": [], "simulated_banner": False}

    q = select(GeneratedAdvisory).where(
        GeneratedAdvisory.panchayat_id == profile.panchayat_id,
        GeneratedAdvisory.approval_status.in_([
            AdvisoryApprovalStatus.APPROVED,
            AdvisoryApprovalStatus.AUTO_APPROVED,
        ]),
    ).order_by(GeneratedAdvisory.created_at.desc()).limit(20)

    result = await db.execute(q)
    advisories = result.scalars().all()

    lang = profile.preferred_language or "en"
    items = []
    for adv in advisories:
        is_sim = adv.data_source.value == "SIMULATED"
        item = {
            "id": adv.id,
            "severity": adv.severity.value,
            "headline": adv.headline,
            "content": adv.content,
            "crop_type": adv.crop_type,
            "data_source": adv.data_source.value,
            "simulated_banner": is_sim,
            "audio_url": adv.audio_url,
            "created_at": adv.created_at.isoformat(),
        }
        if lang != "en":
            tr = translate_advisory(adv.headline, adv.content, lang)
            item["headline"] = tr["headline"]
            item["content"]  = tr["content"]
            item["machine_translated"] = tr["machine_translated"]
        items.append(item)

    has_simulated = any(a.data_source.value == "SIMULATED" for a in advisories)
    return {"advisories": items, "simulated_banner": has_simulated}


@router.get("/{advisory_id}", summary="Advisory detail")
async def get_advisory(
    advisory_id: int,
    lang: str = "en",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(GeneratedAdvisory).where(GeneratedAdvisory.id == advisory_id)
    )
    adv = result.scalar_one_or_none()
    if not adv:
        raise HTTPException(status_code=404, detail="Advisory not found")

    response = {
        "id": adv.id,
        "severity": adv.severity.value,
        "approval_status": adv.approval_status.value,
        "headline": adv.headline,
        "content": adv.content,
        "crop_type": adv.crop_type,
        "data_source": adv.data_source.value,
        "simulated_banner": adv.data_source.value == "SIMULATED",
        "audio_url": adv.audio_url,
        "created_at": adv.created_at.isoformat(),
        "language": lang,
        "machine_translated": False,
    }

    if lang != "en":
        if lang not in SUPPORTED_LANGUAGES:
            raise HTTPException(status_code=400, detail=f"Unsupported language: {lang}")
        tr = translate_advisory(adv.headline, adv.content, lang)
        response.update({
            "headline":         tr["headline"],
            "content":          tr["content"],
            "machine_translated": tr["machine_translated"],
            "language":         lang,
        })
    return response


@router.get("/{advisory_id}/translate/{lang}", summary="On-demand translation")
async def translate_advisory_endpoint(
    advisory_id: int,
    lang: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if lang not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported language: {lang}")

    result = await db.execute(
        select(GeneratedAdvisory).where(GeneratedAdvisory.id == advisory_id)
    )
    adv = result.scalar_one_or_none()
    if not adv:
        raise HTTPException(status_code=404, detail="Advisory not found")

    return translate_advisory(adv.headline, adv.content, lang)
