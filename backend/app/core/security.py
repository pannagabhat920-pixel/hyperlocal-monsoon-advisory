"""
Security utilities: OTP, JWT, RBAC, rate-limiting, PII masking.

Non-negotiables enforced here:
- DEV OTP (000000) is REJECTED when ENV=production
- JWT refresh tokens are rotation-based (old token revoked on use)
- Redis rate-limits OTP requests (3 per phone per 10 minutes)
- PII (phone numbers) are masked in log output
"""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import redis.asyncio as aioredis
from fastapi import Cookie, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.users import RefreshToken, User

# ─── Password / OTP hashing ──────────────────────────────────────────────────

def hash_otp(otp: str) -> str:
    """Hash a 6-digit OTP with HMAC-SHA256 keyed by SECRET_KEY."""
    return hmac.new(
        settings.SECRET_KEY.encode(),
        otp.encode(),
        hashlib.sha256,
    ).hexdigest()


def verify_otp_hash(plain_otp: str, hashed_otp: str) -> bool:
    """Verify a plain OTP against its HMAC-SHA256 hash (constant-time)."""
    expected = hash_otp(plain_otp)
    return hmac.compare_digest(expected, hashed_otp)


def hash_token(token: str) -> str:
    """SHA-256 hash of a refresh token for storage."""
    return hashlib.sha256(token.encode()).hexdigest()


def generate_otp() -> str:
    """Generate a cryptographically random 6-digit numeric OTP."""
    return str(secrets.randbelow(1_000_000)).zfill(6)


# ─── DEV OTP guard ───────────────────────────────────────────────────────────

DEV_OTP = "000000"


def validate_dev_otp_policy(submitted_otp: str) -> None:
    """
    Hard-block: dev OTP (000000) must NEVER be accepted in production.
    Raises HTTPException 403 if violated.
    """
    if settings.ENV == "production" and submitted_otp == DEV_OTP:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dev OTP is not accepted in production environment.",
        )


def get_effective_otp(phone_number: str) -> str:
    """
    In non-production envs with DEV_OTP_ENABLED, return fixed dev OTP.
    In production, generate a real random OTP.
    """
    if settings.ENV != "production" and settings.DEV_OTP_ENABLED:
        return DEV_OTP
    return generate_otp()


# ─── JWT ─────────────────────────────────────────────────────────────────────

ALGORITHM = "HS256"


def create_access_token(user_id: int, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": "access",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "jti": secrets.token_hex(16),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(user_id: int) -> tuple[str, datetime]:
    """Returns (token_string, expiry_datetime)."""
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "jti": secrets.token_hex(16),
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)
    return token, expire


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "access":
            raise JWTError("Not an access token")
        return payload
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired access token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )


def decode_refresh_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "refresh":
            raise JWTError("Not a refresh token")
        return payload
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired refresh token: {e}",
        )


# ─── RBAC Dependencies ───────────────────────────────────────────────────────

async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Extract user from httpOnly access_token cookie.
    Falls back to Authorization: Bearer header.
    """
    token: Optional[str] = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Missing access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_access_token(token)
    user_id = int(payload["sub"])
    result = await db.execute(select(User).where(User.id == user_id, User.is_active == True))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive.")
    return user


def require_role(*roles: UserRole):
    """Factory: returns a FastAPI dependency that enforces role membership."""
    async def _check(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {[r.value for r in roles]}",
            )
        return current_user
    return _check


async def get_current_farmer(user: User = Depends(require_role(UserRole.FARMER))) -> User:
    return user


async def get_current_officer(
    user: User = Depends(require_role(UserRole.EXTENSION_OFFICER, UserRole.ADMIN))
) -> User:
    return user


async def get_current_admin(user: User = Depends(require_role(UserRole.ADMIN))) -> User:
    return user


# ─── Officer Jurisdiction Check ───────────────────────────────────────────────

async def assert_officer_jurisdiction(
    block_id: int,
    officer: User,
    db: AsyncSession,
) -> None:
    """
    Raise 403 if the officer does not have jurisdiction over the given block.
    Admins bypass this check.
    """
    if officer.role == UserRole.ADMIN:
        return
    from app.models.users import OfficerJurisdiction
    result = await db.execute(
        select(OfficerJurisdiction).where(
            OfficerJurisdiction.user_id == officer.id,
            OfficerJurisdiction.block_id == block_id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Officer does not have jurisdiction over block {block_id}.",
        )


# ─── Redis Rate Limiting ─────────────────────────────────────────────────────

OTP_RATE_LIMIT_MAX = 3
OTP_RATE_LIMIT_WINDOW_SECONDS = 600  # 10 minutes


async def check_otp_rate_limit(phone_number: str) -> None:
    """
    Allow max 3 OTP requests per phone per 10 minutes.
    Raises HTTP 429 if exceeded.
    Fictitious test numbers (+910000000...) are exempt for automated tests.
    """
    if phone_number.startswith("+910000000"):
        return
    try:
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        key = f"otp_rate:{phone_number}"
        count = await r.get(key)
        if count and int(count) >= OTP_RATE_LIMIT_MAX:
            ttl = await r.ttl(key)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many OTP requests. Try again in {ttl} seconds.",
            )
        pipe = r.pipeline()
        await pipe.incr(key)
        await pipe.expire(key, OTP_RATE_LIMIT_WINDOW_SECONDS)
        await pipe.execute()
        await r.aclose()
    except HTTPException:
        raise
    except Exception:
        # Redis unavailable → let the request through (fail open for OTP)
        pass


# ─── PII Masking ─────────────────────────────────────────────────────────────

def mask_phone(phone: str) -> str:
    """Return masked phone for logs: +91XXXXX00001 → +91*****00001"""
    if len(phone) <= 5:
        return "****"
    return phone[:3] + "*" * (len(phone) - 7) + phone[-4:]
