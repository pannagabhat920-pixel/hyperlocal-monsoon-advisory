from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.enums import IrrigationSource
from app.models.users import FarmerProfile, User

router = APIRouter(prefix="/api/v1/me", tags=["Me"])


# ─── Schemas ─────────────────────────────────────────────────────────────────

class ProfileOut(BaseModel):
    user_id: int
    phone_number: str
    role: str
    preferred_language: str
    is_active: bool
    consent_given_at: Optional[datetime]
    panchayat_id: Optional[int]
    crop_type: Optional[str]
    crop_status: Optional[str]
    irrigation_source: Optional[str]
    farm_size_acres: Optional[float]
    soil_type: Optional[str]
    whatsapp_consent: bool = True
    sms_consent: bool = True
    opted_out_at: Optional[datetime] = None


class ProfilePatchIn(BaseModel):
    preferred_language: Optional[str] = None
    panchayat_id: Optional[int] = None
    crop_type: Optional[str] = None
    irrigation_source: Optional[IrrigationSource] = None
    farm_size_acres: Optional[float] = None
    soil_type: Optional[str] = None
    whatsapp_consent: Optional[bool] = None
    sms_consent: Optional[bool] = None
    opt_out: Optional[bool] = None


class CropStatusPatchIn(BaseModel):
    crop_status: str


# ─── Routes ──────────────────────────────────────────────────────────────────

@router.get("", response_model=ProfileOut, summary="Get my profile")
async def get_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileOut:
    profile_result = await db.execute(
        select(FarmerProfile).where(FarmerProfile.user_id == current_user.id)
    )
    profile = profile_result.scalar_one_or_none()

    return ProfileOut(
        user_id=current_user.id,
        phone_number=current_user.phone_number,
        role=current_user.role.value,
        preferred_language=current_user.preferred_language,
        is_active=current_user.is_active,
        consent_given_at=current_user.consent_given_at,
        panchayat_id=profile.panchayat_id if profile else None,
        crop_type=profile.crop_type if profile else None,
        crop_status=profile.crop_status if profile else None,
        irrigation_source=profile.irrigation_source.value if profile else None,
        farm_size_acres=profile.farm_size_acres if profile else None,
        soil_type=profile.soil_type if profile else None,
        whatsapp_consent=getattr(current_user, "whatsapp_consent", True),
        sms_consent=getattr(current_user, "sms_consent", True),
        opted_out_at=getattr(current_user, "opted_out_at", None),
    )


@router.patch("", response_model=ProfileOut, summary="Update my profile")
async def update_profile(
    body: ProfilePatchIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileOut:
    if body.preferred_language:
        current_user.preferred_language = body.preferred_language
    if body.whatsapp_consent is not None:
        current_user.whatsapp_consent = body.whatsapp_consent
    if body.sms_consent is not None:
        current_user.sms_consent = body.sms_consent
    if body.opt_out is True:
        current_user.opted_out_at = datetime.now(timezone.utc).replace(tzinfo=None)
    elif body.opt_out is False:
        current_user.opted_out_at = None

    profile_result = await db.execute(
        select(FarmerProfile).where(FarmerProfile.user_id == current_user.id)
    )
    profile = profile_result.scalar_one_or_none()
    if not profile:
        profile = FarmerProfile(user_id=current_user.id, crop_type="unknown")
        db.add(profile)

    if body.panchayat_id is not None:
        profile.panchayat_id = body.panchayat_id
    if body.crop_type:
        profile.crop_type = body.crop_type
    if body.irrigation_source:
        profile.irrigation_source = body.irrigation_source
    if body.farm_size_acres is not None:
        profile.farm_size_acres = body.farm_size_acres
    if body.soil_type:
        profile.soil_type = body.soil_type

    await db.commit()
    await db.refresh(current_user)
    return await get_profile(current_user, db)


@router.patch("/crop-status", summary="1-tap crop status update")
async def update_crop_status(
    body: CropStatusPatchIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    STATUS_ALIASES = {
        "PLANNED": "NOT_STARTED",
        "SOWING": "SOWN",
        "FLOWERING": "FLOWERING_PODDING",
        "TRANSPLANTING": "FLOWERING_PODDING",
        "GRAIN_FILLING": "FLOWERING_PODDING",
        "HARVESTING": "HARVEST_READY",
        "HARVESTED": "HARVEST_READY",
    }
    canonical_status = STATUS_ALIASES.get(body.crop_status.upper(), body.crop_status.upper())
    VALID_STATUSES = {
        "NOT_STARTED", "SOWN", "VEGETATIVE", "FLOWERING_PODDING", "HARVEST_READY"
    }
    if canonical_status not in VALID_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid crop status. Must be one of: {sorted(VALID_STATUSES)}",
        )
    profile_result = await db.execute(
        select(FarmerProfile).where(FarmerProfile.user_id == current_user.id)
    )
    profile = profile_result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Farmer profile not found. Complete onboarding first.")

    profile.crop_status = canonical_status
    await db.commit()
    return {
        "message": "Crop status updated",
        "crop_status": body.crop_status,
        "canonical_status": canonical_status,
    }


@router.delete("", summary="Deactivate my account")
async def delete_account(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Soft-delete: sets is_active=False and records timestamp."""
    current_user.is_active = False
    # Revoke all active refresh tokens
    from app.models.users import RefreshToken
    tokens_result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.user_id == current_user.id,
            RefreshToken.revoked_at == None,
        )
    )
    for token in tokens_result.scalars().all():
        token.revoked_at = datetime.now(timezone.utc).replace(tzinfo=None)

    await db.commit()
    return {"message": "Account deactivated. Your data will be deleted within 30 days per our privacy policy."}
