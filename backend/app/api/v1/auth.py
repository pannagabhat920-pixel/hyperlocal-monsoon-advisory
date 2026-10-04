from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    assert_officer_jurisdiction,
    check_otp_rate_limit,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    get_current_user,
    get_effective_otp,
    hash_otp,
    hash_token,
    mask_phone,
    validate_dev_otp_policy,
    verify_otp_hash,
)
from app.db.session import get_db
from app.models.enums import IrrigationSource, UserRole
from app.models.users import FarmerProfile, OTPVerification, RefreshToken, User

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])

OTP_EXPIRY_MINUTES = 5
MAX_OTP_ATTEMPTS = 5

# ─── Schemas ─────────────────────────────────────────────────────────────────

class RequestOTPIn(BaseModel):
    phone_number: str

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith("+"):
            raise ValueError("Phone number must start with country code, e.g. +91XXXXXXXXXX")
        digits = v[1:].replace(" ", "")
        if not digits.isdigit() or len(digits) < 7 or len(digits) > 15:
            raise ValueError("Invalid phone number format")
        return v


class VerifyOTPIn(BaseModel):
    phone_number: str
    otp: str


class OnboardingIn(BaseModel):
    panchayat_id: Optional[int] = None
    crop_type: Optional[str] = None
    irrigation_source: Optional[IrrigationSource] = None
    farm_size_acres: Optional[float] = None
    soil_type: Optional[str] = None
    consent: bool = False
    preferred_language: Optional[str] = None


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    is_prod = settings.ENV == "production"
    response.set_cookie(
        "access_token", access_token,
        httponly=True, secure=is_prod, samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )
    response.set_cookie(
        "refresh_token", refresh_token,
        httponly=True, secure=is_prod, samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/api/v1/auth/refresh",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/api/v1/auth/refresh")


# ─── Routes ──────────────────────────────────────────────────────────────────

@router.post("/request-otp", summary="Request OTP for phone login")
async def request_otp(
    body: RequestOTPIn,
    db: AsyncSession = Depends(get_db),
) -> dict:
    await check_otp_rate_limit(body.phone_number)

    otp = get_effective_otp(body.phone_number)
    otp_hash = hash_otp(otp)
    expiry = datetime.now(timezone.utc) + timedelta(minutes=OTP_EXPIRY_MINUTES)

    # Expire old OTPs for this number
    old_otps = await db.execute(
        select(OTPVerification).where(
            OTPVerification.phone_number == body.phone_number,
            OTPVerification.is_verified == False,
        )
    )
    for old in old_otps.scalars().all():
        old.is_verified = True  # Invalidate

    new_otp = OTPVerification(
        phone_number=body.phone_number,
        otp_hash=otp_hash,
        expires_at=expiry.replace(tzinfo=None),
    )
    db.add(new_otp)
    await db.commit()

    # In dev/test, return OTP directly (no real SMS)
    if settings.ENV != "production" and settings.MESSAGING_PROVIDER in ("mock", "console"):
        return {
            "message": f"OTP sent to {mask_phone(body.phone_number)}",
            "_dev_otp": otp,  # Never present in production
        }

    # Production: dispatch via messaging gateway (Phase 4)
    return {"message": f"OTP sent to {mask_phone(body.phone_number)}"}


@router.post("/verify-otp", summary="Verify OTP and issue JWT tokens")
async def verify_otp(
    body: VerifyOTPIn,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> dict:
    # Hard-block dev OTP in production
    validate_dev_otp_policy(body.otp)

    # Find the latest unverified OTP for this phone
    result = await db.execute(
        select(OTPVerification).where(
            OTPVerification.phone_number == body.phone_number,
            OTPVerification.is_verified == False,
        ).order_by(OTPVerification.created_at.desc()).limit(1)
    )
    otp_record = result.scalar_one_or_none()

    if not otp_record:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No pending OTP found. Please request a new one.")

    # Check expiry — normalize to naive UTC regardless of DB column tz-awareness
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    expires_at = otp_record.expires_at
    if hasattr(expires_at, 'tzinfo') and expires_at.tzinfo is not None:
        expires_at = expires_at.replace(tzinfo=None)
    if expires_at < now:
        otp_record.is_verified = True
        await db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP has expired. Please request a new one.")


    # Check attempt count
    otp_record.attempts += 1
    if otp_record.attempts > MAX_OTP_ATTEMPTS:
        otp_record.is_verified = True
        await db.commit()
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many incorrect attempts. Request a new OTP.")

    # Verify hash
    if not verify_otp_hash(body.otp, otp_record.otp_hash):
        await db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect OTP.")

    # Mark as verified
    otp_record.is_verified = True
    await db.commit()

    # Upsert user
    user_result = await db.execute(select(User).where(User.phone_number == body.phone_number))
    user = user_result.scalar_one_or_none()
    if not user:
        user = User(phone_number=body.phone_number, role=UserRole.FARMER)
        db.add(user)
        await db.flush()

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated.")

    # Issue tokens
    access_token = create_access_token(user.id, user.role.value)
    refresh_token_str, refresh_expiry = create_refresh_token(user.id)

    rt = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(refresh_token_str),
        expires_at=refresh_expiry.replace(tzinfo=None),
    )
    db.add(rt)
    await db.commit()

    _set_auth_cookies(response, access_token, refresh_token_str)

    # Check if new user (to prompt onboarding)
    profile_check = None
    if user.role == UserRole.FARMER:
        profile_result = await db.execute(
            select(FarmerProfile).where(FarmerProfile.user_id == user.id)
        )
        profile_check = profile_result.scalar_one_or_none()
    is_new_user = profile_check is None if user.role == UserRole.FARMER else False

    return {
        "user_id": user.id,
        "role": user.role.value,
        "is_new_user": is_new_user,
        "message": "Login successful",
    }


@router.post("/refresh", summary="Rotate JWT access + refresh tokens")
async def refresh_tokens(
    response: Response,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    refresh_token_str: str | None = request.cookies.get("refresh_token")
    if not refresh_token_str:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token found.")

    payload = decode_refresh_token(refresh_token_str)
    user_id = int(payload["sub"])

    # Verify token exists in DB and is not revoked
    token_hash = hash_token(refresh_token_str)
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked_at == None,
        )
    )
    rt = result.scalar_one_or_none()
    if not rt:
        _clear_auth_cookies(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token revoked or not found.")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rt_expires = rt.expires_at
    if hasattr(rt_expires, 'tzinfo') and rt_expires.tzinfo is not None:
        rt_expires = rt_expires.replace(tzinfo=None)
    if rt_expires < now:
        _clear_auth_cookies(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired.")


    # Revoke old refresh token
    rt.revoked_at = datetime.now(timezone.utc).replace(tzinfo=None)

    # Get user
    user_result = await db.execute(select(User).where(User.id == user_id, User.is_active == True))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive.")

    # Issue new tokens
    new_access = create_access_token(user.id, user.role.value)
    new_refresh_str, new_expiry = create_refresh_token(user.id)
    new_rt = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(new_refresh_str),
        expires_at=new_expiry.replace(tzinfo=None),
    )
    db.add(new_rt)
    await db.commit()

    _set_auth_cookies(response, new_access, new_refresh_str)
    return {"message": "Tokens refreshed"}


@router.post("/logout", summary="Logout and revoke refresh token")
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> dict:
    refresh_token_str: str | None = request.cookies.get("refresh_token")
    if refresh_token_str:
        token_hash = hash_token(refresh_token_str)
        result = await db.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.revoked_at == None,
            )
        )
        rt = result.scalar_one_or_none()
        if rt:
            rt.revoked_at = datetime.now(timezone.utc).replace(tzinfo=None)
            await db.commit()
    _clear_auth_cookies(response)
    return {"message": "Logged out"}


@router.post("/onboarding", summary="Complete farmer onboarding with consent")
async def onboarding(
    body: OnboardingIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if not body.consent:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Consent is required to complete onboarding.")

    # Record consent timestamp
    current_user.consent_given_at = datetime.now(timezone.utc).replace(tzinfo=None)
    if body.preferred_language:
        current_user.preferred_language = body.preferred_language

    # Update or create FarmerProfile
    profile_result = await db.execute(
        select(FarmerProfile).where(FarmerProfile.user_id == current_user.id)
    )
    profile = profile_result.scalar_one_or_none()

    if profile is None:
        profile = FarmerProfile(
            user_id=current_user.id,
            crop_type=body.crop_type or "unknown",
        )
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
    return {"message": "Onboarding complete", "user_id": current_user.id}
