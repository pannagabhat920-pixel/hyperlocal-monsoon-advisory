"""
Officer portal endpoints.

GET  /api/v1/officer/queue                      - Pending approval queue
POST /api/v1/officer/advisories/{id}/approve    - Approve advisory
POST /api/v1/officer/advisories/{id}/reject     - Reject advisory
GET  /api/v1/officer/advisories/{id}/translate/{lang} - Translation preview
POST /api/v1/officer/broadcast                  - Broadcast approved advisories to farmers
GET  /api/v1/officer/delivery                   - Delivery status for officer's jurisdiction
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    assert_officer_jurisdiction,
    get_current_farmer,
    get_current_officer,
    get_current_user,
    require_role,
)
from app.db.session import get_db
from app.models.agronomy import GeneratedAdvisory, NotificationLog
from app.models.enums import (
    AdvisoryApprovalStatus,
    AdvisorySeverity,
    NotificationChannel,
    NotificationStatus,
    UserRole,
)
from app.models.geography import Block, Panchayat
from app.models.users import FarmerProfile, OfficerJurisdiction, User
from app.services.messaging_gateway import dispatch_notification
from app.services.translation import SUPPORTED_LANGUAGES, translate_advisory

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/officer", tags=["Officer"])


class ApproveBody(BaseModel):
    notes: Optional[str] = None


class BroadcastBody(BaseModel):
    advisory_ids: list[int]
    channel: str = "SMS"
    confirm: bool = False  # Must be True to actually broadcast


# ─── Approval Queue ───────────────────────────────────────────────────────────

@router.get("/queue", summary="Pending advisory approval queue")
async def approval_queue(
    block_id: Optional[int] = None,
    current_user: User = Depends(get_current_officer),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns PENDING advisories within the officer's jurisdiction.
    CRITICAL advisories appear first.
    """
    # Get officer's jurisdiction block IDs
    jur_result = await db.execute(
        select(OfficerJurisdiction.block_id).where(
            OfficerJurisdiction.user_id == current_user.id
        )
    )
    jurisdiction_block_ids = [r[0] for r in jur_result.all()]

    # Admins see everything
    if current_user.role == UserRole.ADMIN:
        jurisdiction_block_ids = None  # No filter

    q = select(GeneratedAdvisory).where(
        GeneratedAdvisory.approval_status == AdvisoryApprovalStatus.PENDING
    )
    if jurisdiction_block_ids is not None:
        if block_id:
            q = q.where(GeneratedAdvisory.block_id == block_id)
        else:
            q = q.where(GeneratedAdvisory.block_id.in_(jurisdiction_block_ids))
    elif block_id:
        q = q.where(GeneratedAdvisory.block_id == block_id)

    # CRITICAL first, then HIGH, then creation order
    q = q.order_by(
        GeneratedAdvisory.severity.desc(),
        GeneratedAdvisory.created_at.desc(),
    )

    result = await db.execute(q)
    advisories = result.scalars().all()

    items = [
        {
            "id": a.id,
            "severity": a.severity.value,
            "crop_type": a.crop_type,
            "headline": a.headline,
            "data_source": a.data_source.value,
            "simulated_banner": a.data_source.value == "SIMULATED",
            "block_id": a.block_id,
            "panchayat_id": a.panchayat_id,
            "created_at": a.created_at.isoformat(),
        }
        for a in advisories
    ]
    return {
        "count": len(advisories),
        "advisories": items,
        "queue": items,
    }


# ─── Approve / Reject ─────────────────────────────────────────────────────────

@router.post("/advisories/{advisory_id}/approve", summary="Approve an advisory")
async def approve_advisory(
    advisory_id: int,
    body: ApproveBody = Body(default=ApproveBody()),
    current_user: User = Depends(get_current_officer),
    db: AsyncSession = Depends(get_db),
):
    adv = await _get_advisory_or_404(advisory_id, db)
    await assert_officer_jurisdiction(adv.block_id, current_user, db)

    if adv.approval_status != AdvisoryApprovalStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Advisory is already {adv.approval_status.value}",
        )

    adv.approval_status         = AdvisoryApprovalStatus.APPROVED
    adv.approved_by_officer_id  = current_user.id
    adv.approved_at             = datetime.now(timezone.utc)

    # Pre-generate and cache TTS audio for the advisory
    from app.services.tts import generate_tts_audio
    adv.audio_url = generate_tts_audio(adv.content, language=adv.language or "en")

    await db.commit()

    logger.info(f"[Officer] Approved advisory {advisory_id} by officer {current_user.id} with cached TTS: {adv.audio_url}")
    return {"message": "Advisory approved", "advisory_id": advisory_id, "audio_url": adv.audio_url}



@router.post("/advisories/{advisory_id}/reject", summary="Reject an advisory")
async def reject_advisory(
    advisory_id: int,
    body: ApproveBody = Body(default=ApproveBody()),
    current_user: User = Depends(get_current_officer),
    db: AsyncSession = Depends(get_db),
):
    adv = await _get_advisory_or_404(advisory_id, db)
    await assert_officer_jurisdiction(adv.block_id, current_user, db)

    if adv.approval_status != AdvisoryApprovalStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Advisory is already {adv.approval_status.value}",
        )

    adv.approval_status = AdvisoryApprovalStatus.REJECTED
    await db.commit()

    logger.info(f"[Officer] Rejected advisory {advisory_id} by officer {current_user.id}")
    return {"message": "Advisory rejected", "advisory_id": advisory_id}


# ─── Translation Preview ──────────────────────────────────────────────────────

@router.get("/advisories/{advisory_id}/translate/{lang}", summary="Translation preview")
async def translation_preview(
    advisory_id: int,
    lang: str,
    current_user: User = Depends(get_current_officer),
    db: AsyncSession = Depends(get_db),
):
    if lang not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported language: {lang}")

    adv = await _get_advisory_or_404(advisory_id, db)
    preview = translate_advisory(adv.headline, adv.content, lang)
    preview["simulated_banner"] = adv.data_source.value == "SIMULATED"
    preview["flagged_for_review"] = preview.get("machine_translated", False)
    preview["review_required"] = preview.get("machine_translated", False)
    if preview.get("machine_translated"):
        preview["review_disclaimer"] = "Machine-translated content: Extension Officer review required before broadcast."
    return preview


# ─── Broadcast ────────────────────────────────────────────────────────────────

@router.post("/broadcast", summary="Broadcast approved advisories to farmers")
async def broadcast_advisories(
    body: BroadcastBody,
    current_user: User = Depends(get_current_officer),
    db: AsyncSession = Depends(get_db),
):
    """
    Dispatch approved advisories to all farmers in the relevant panchayats.

    Safety:
      - confirm=False → dry-run, returns what would be sent
      - SIMULATED advisories → BLOCKED_SIMULATED, never reach provider
      - Only officers with jurisdiction over the advisory's block may broadcast
      - Enforces farmer-level 72h cooldown (CRITICAL alerts bypass)
      - Enforces farmer consent / opt-out
    """
    from app.services.agronomy_engine import check_farmer_cooldown

    if not body.advisory_ids:
        raise HTTPException(status_code=400, detail="advisory_ids cannot be empty")

    try:
        channel = NotificationChannel(body.channel.upper())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid channel: {body.channel}")

    results = []
    for advisory_id in body.advisory_ids:
        adv = await _get_advisory_or_404(advisory_id, db)
        await assert_officer_jurisdiction(adv.block_id, current_user, db)

        if adv.approval_status not in (
            AdvisoryApprovalStatus.APPROVED,
            AdvisoryApprovalStatus.AUTO_APPROVED,
        ):
            results.append({
                "advisory_id": advisory_id,
                "error": f"Cannot broadcast: status={adv.approval_status.value}",
            })
            continue

        # Find farmers in this panchayat
        farmers_result = await db.execute(
            select(FarmerProfile, User).join(User, FarmerProfile.user_id == User.id).where(
                FarmerProfile.panchayat_id == adv.panchayat_id,
                User.is_active == True,
            )
        )
        farmers = farmers_result.all()

        dispatched = 0
        blocked_simulated = 0
        blocked_cooldown = 0
        dry_run_count = 0

        for profile, farmer in farmers:
            # Consent check
            if not farmer.consent_given_at or not farmer.is_active:
                continue

            # Farmer-level 72h cooldown with CRITICAL escalation exception
            allowed_cooldown = await check_farmer_cooldown(farmer.id, adv.severity, db)
            if not allowed_cooldown:
                blocked_cooldown += 1
                continue

            lang = farmer.preferred_language or "en"
            if lang != "en":
                tr = translate_advisory(adv.headline, adv.content, lang)
                message_body = f"{tr['headline']}\n\n{tr['content']}"
                if tr["machine_translated"]:
                    message_body += "\n[Machine translated]"
            else:
                message_body = f"{adv.headline}\n\n{adv.content}"

            if adv.data_source.value == "SIMULATED":
                message_body = "[SIMULATED DATA — NOT FOR REAL USE]\n" + message_body

            if not body.confirm:
                dry_run_count += 1
                continue

            log = await dispatch_notification(
                advisory       =adv,
                recipient_phone=farmer.phone_number,
                recipient_id   =farmer.id,
                message_body   =message_body,
                channel        =channel,
                db             =db,
            )
            if log.dispatch_status == NotificationStatus.BLOCKED_SIMULATED:
                blocked_simulated += 1
            else:
                dispatched += 1

        results.append({
            "advisory_id":          advisory_id,
            "simulated":            adv.data_source.value == "SIMULATED",
            "farmers_in_panchayat": len(farmers),
            "dispatched":           dispatched,
            "blocked_simulated":    blocked_simulated,
            "blocked_cooldown":     blocked_cooldown,
            "dry_run":              dry_run_count if not body.confirm else 0,
            "confirmed":            body.confirm,
        })


    return {"results": results}


# ─── Delivery Status ──────────────────────────────────────────────────────────

@router.get("/delivery", summary="Delivery status for recent notifications")
async def delivery_status(
    advisory_id: Optional[int] = None,
    current_user: User = Depends(get_current_officer),
    db: AsyncSession = Depends(get_db),
):
    q = select(NotificationLog).order_by(NotificationLog.created_at.desc()).limit(100)
    if advisory_id:
        q = q.where(NotificationLog.advisory_id == advisory_id)

    result = await db.execute(q)
    logs = result.scalars().all()

    return {
        "count": len(logs),
        "logs": [
            {
                "id": log.id,
                "advisory_id": log.advisory_id,
                "channel": log.channel.value,
                "status": log.dispatch_status.value,
                "provider_message_id": log.provider_message_id,
                "attempt_count": log.attempt_count,
                "created_at": log.created_at.isoformat(),
            }
            for log in logs
        ],
    }


# ─── Helper ───────────────────────────────────────────────────────────────────

async def _get_advisory_or_404(advisory_id: int, db: AsyncSession) -> GeneratedAdvisory:
    result = await db.execute(
        select(GeneratedAdvisory).where(GeneratedAdvisory.id == advisory_id)
    )
    adv = result.scalar_one_or_none()
    if not adv:
        raise HTTPException(status_code=404, detail="Advisory not found")
    return adv
