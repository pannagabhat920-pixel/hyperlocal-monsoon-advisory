"""
Phase 2 Auth & Users Tests.

Non-negotiable gates:
- Dev OTP (000000) REJECTED when ENV=production
- Officer jurisdiction enforced
- JWT refresh rotation (old token revoked on use)
- No duplicate user created on repeat login
- Consent required for onboarding
- PII masking works correctly
"""
import asyncio
import os

import pytest
import redis as sync_redis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# env vars set by conftest.py before imports
DATABASE_URL = os.environ["DATABASE_URL"]
REDIS_URL = os.environ["REDIS_URL"]
DEV_OTP = "000000"

# Phone counter — each test gets its own unique number
_COUNTER = iter(range(931_111_0001, 931_119_9999))


def fresh_phone() -> str:
    return f"+91{next(_COUNTER)}"


def clear_rl(phone: str) -> None:
    """Clear OTP rate-limit key in Redis synchronously."""
    try:
        r = sync_redis.from_url(REDIS_URL)
        r.delete(f"otp_rate:{phone}")
        r.close()
    except Exception:
        pass


def make_engine():
    return create_async_engine(DATABASE_URL, poolclass=NullPool)


async def override_get_db():
    """Dependency override: NullPool session so no cross-loop connection reuse."""
    engine = make_engine()
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as session:
        yield session
    await engine.dispose()


def make_client():
    """Build a test AsyncClient with the DB dependency overridden."""
    from app.main import app
    from app.db.session import get_db
    app.dependency_overrides[get_db] = override_get_db
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def do_login(client: AsyncClient, phone: str) -> dict:
    """OTP request + verify, returns the verify response."""
    clear_rl(phone)
    r1 = await client.post("/api/v1/auth/request-otp", json={"phone_number": phone})
    assert r1.status_code == 200, f"request-otp failed ({r1.status_code}): {r1.text}"
    r2 = await client.post("/api/v1/auth/verify-otp",
                            json={"phone_number": phone, "otp": DEV_OTP})
    return r2


# ─── OTP Flow ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio(loop_scope="function")
async def test_request_otp_returns_dev_otp_in_test_mode():
    """In test/dev mode, _dev_otp is in response."""
    phone = fresh_phone()
    clear_rl(phone)
    async with make_client() as client:
        resp = await client.post("/api/v1/auth/request-otp", json={"phone_number": phone})
    assert resp.status_code == 200, f"{resp.status_code}: {resp.text}"
    assert resp.json().get("_dev_otp") == DEV_OTP


@pytest.mark.asyncio(loop_scope="function")
async def test_dev_otp_blocked_in_production():
    """000000 must be rejected when ENV=production (hard block)."""
    import app.core.config as cfg
    original = cfg.settings.ENV
    cfg.settings.ENV = "production"
    try:
        async with make_client() as client:
            resp = await client.post("/api/v1/auth/verify-otp",
                                      json={"phone_number": fresh_phone(), "otp": DEV_OTP})
        assert resp.status_code == 403
        assert "production" in resp.json()["detail"].lower()
    finally:
        cfg.settings.ENV = original


@pytest.mark.asyncio(loop_scope="function")
async def test_verify_otp_creates_user_and_issues_tokens():
    """Verify OTP creates a new user and sets auth cookies."""
    phone = fresh_phone()
    async with make_client() as client:
        resp = await do_login(client, phone)
    assert resp.status_code == 200, f"{resp.status_code}: {resp.text}"
    data = resp.json()
    assert "user_id" in data and "role" in data


@pytest.mark.asyncio(loop_scope="function")
async def test_verify_otp_idempotent_user():
    """Two logins for the same phone must create exactly one user."""
    from app.models.users import User
    phone = fresh_phone()

    async with make_client() as client:
        await do_login(client, phone)
        clear_rl(phone)
        await do_login(client, phone)

    engine = make_engine()
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as db:
        result = await db.execute(select(User).where(User.phone_number == phone))
        users = result.scalars().all()
    await engine.dispose()
    assert len(users) == 1


@pytest.mark.asyncio(loop_scope="function")
async def test_invalid_otp_rejected():
    """Wrong OTP → 400."""
    phone = fresh_phone()
    clear_rl(phone)
    async with make_client() as client:
        await client.post("/api/v1/auth/request-otp", json={"phone_number": phone})
        resp = await client.post("/api/v1/auth/verify-otp",
                                  json={"phone_number": phone, "otp": "999999"})
    assert resp.status_code == 400


# ─── JWT & Refresh Rotation ───────────────────────────────────────────────────

@pytest.mark.asyncio(loop_scope="function")
async def test_jwt_rotation_revokes_old_token():
    """After /refresh, original refresh token is rejected."""
    phone = fresh_phone()
    async with make_client() as client:
        login = await do_login(client, phone)
        assert login.status_code == 200
        original_rt = client.cookies.get("refresh_token")
        r1 = await client.post("/api/v1/auth/refresh")
        assert r1.status_code == 200, f"First refresh failed: {r1.text}"
        if original_rt:
            client.cookies.set("refresh_token", original_rt)
            r2 = await client.post("/api/v1/auth/refresh")
            assert r2.status_code == 401, "Revoked refresh token must fail"


@pytest.mark.asyncio(loop_scope="function")
async def test_access_protected_endpoint_without_token():
    """Unauthenticated /me → 401."""
    async with make_client() as client:
        resp = await client.get("/api/v1/me")
    assert resp.status_code == 401


@pytest.mark.asyncio(loop_scope="function")
async def test_get_profile_authenticated():
    """Authenticated /me returns the user's phone number."""
    phone = fresh_phone()
    async with make_client() as client:
        await do_login(client, phone)
        resp = await client.get("/api/v1/me")
    assert resp.status_code == 200, f"{resp.status_code}: {resp.text}"
    assert resp.json()["phone_number"] == phone


# ─── Onboarding & Consent ─────────────────────────────────────────────────────

@pytest.mark.asyncio(loop_scope="function")
async def test_onboarding_requires_consent():
    """Onboarding without consent → 400."""
    phone = fresh_phone()
    async with make_client() as client:
        await do_login(client, phone)
        resp = await client.post("/api/v1/auth/onboarding",
                                  json={"consent": False, "crop_type": "cotton"})
    assert resp.status_code == 400
    assert "consent" in resp.json()["detail"].lower()


@pytest.mark.asyncio(loop_scope="function")
async def test_onboarding_with_consent_succeeds():
    """Onboarding with consent → 200."""
    phone = fresh_phone()
    async with make_client() as client:
        await do_login(client, phone)
        resp = await client.post("/api/v1/auth/onboarding",
                                  json={"consent": True, "crop_type": "cotton",
                                        "irrigation_source": "RAINFED", "preferred_language": "mr"})
    assert resp.status_code == 200
    assert resp.json()["message"] == "Onboarding complete"


# ─── 1-tap crop status ────────────────────────────────────────────────────────

@pytest.mark.asyncio(loop_scope="function")
async def test_crop_status_valid_update():
    """PATCH /me/crop-status with valid status → 200."""
    phone = fresh_phone()
    async with make_client() as client:
        await do_login(client, phone)
        await client.post("/api/v1/auth/onboarding",
                           json={"consent": True, "crop_type": "cotton"})
        resp = await client.patch("/api/v1/me/crop-status", json={"crop_status": "FLOWERING"})
    assert resp.status_code == 200
    assert resp.json()["crop_status"] == "FLOWERING"


@pytest.mark.asyncio(loop_scope="function")
async def test_crop_status_invalid_rejected():
    """PATCH /me/crop-status with bad value → 400."""
    phone = fresh_phone()
    async with make_client() as client:
        await do_login(client, phone)
        await client.post("/api/v1/auth/onboarding",
                           json={"consent": True, "crop_type": "soybean"})
        resp = await client.patch("/api/v1/me/crop-status", json={"crop_status": "FLYING"})
    assert resp.status_code == 400


# ─── Logout ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio(loop_scope="function")
async def test_logout_clears_session():
    """After logout, /me → 401."""
    phone = fresh_phone()
    async with make_client() as client:
        await do_login(client, phone)
        logout = await client.post("/api/v1/auth/logout")
        assert logout.status_code == 200
        me = await client.get("/api/v1/me")
    assert me.status_code == 401


# ─── Officer Jurisdiction ─────────────────────────────────────────────────────

@pytest.mark.asyncio(loop_scope="function")
async def test_officer_jurisdiction_enforced():
    """Officer without access to a block → 403."""
    from app.core.security import assert_officer_jurisdiction
    from app.models.enums import UserRole
    from app.models.users import User

    engine = make_engine()
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as db:
        officer = User(phone_number=fresh_phone(), role=UserRole.EXTENSION_OFFICER)
        db.add(officer)
        await db.flush()
        with pytest.raises(Exception) as exc:
            await assert_officer_jurisdiction(99999, officer, db)
        assert exc.value.status_code == 403
    await engine.dispose()


@pytest.mark.asyncio(loop_scope="function")
async def test_admin_bypasses_jurisdiction_check():
    """Admin → jurisdiction check never raises."""
    from app.core.security import assert_officer_jurisdiction
    from app.models.enums import UserRole
    from app.models.users import User

    engine = make_engine()
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as db:
        admin = User(phone_number=fresh_phone(), role=UserRole.ADMIN)
        db.add(admin)
        await db.flush()
        await assert_officer_jurisdiction(99999, admin, db)  # Must not raise
    await engine.dispose()


# ─── PII Masking ─────────────────────────────────────────────────────────────

def test_phone_masking():
    """mask_phone hides middle digits, keeps prefix and last 4."""
    from app.core.security import mask_phone
    masked = mask_phone("+919999900001")
    assert masked.startswith("+91")
    assert "0001" in masked
    assert "*" in masked
    assert masked.count("*") >= 3


# ─── Production Security & Validation ────────────────────────────────────────

def test_production_phone_format_validation():
    """In production, Indian numbers must match +91[6-9]XXXXXXXXX; test numbers are rejected."""
    from app.core import config as cfg
    from app.api.v1.auth import RequestOTPIn
    from pydantic import ValidationError

    original = cfg.settings.ENV
    cfg.settings.ENV = "production"
    try:
        # Valid Indian mobile number in production (starts with 6-9)
        valid = RequestOTPIn(phone_number="+919876543210")
        assert valid.phone_number == "+919876543210"

        # Fictitious number starting with 0 is rejected in production
        with pytest.raises(ValidationError, match="Indian mobile numbers must be 10 digits starting with 6-9"):
            RequestOTPIn(phone_number="+910000000001")
    finally:
        cfg.settings.ENV = original


@pytest.mark.asyncio(loop_scope="function")
async def test_production_rate_limit_exemption_disabled():
    """In production, rate-limit exemption for +910000000xxx is strictly disabled."""
    from app.core import config as cfg
    from app.core.security import check_otp_rate_limit
    import redis.asyncio as aioredis
    from fastapi import HTTPException

    original = cfg.settings.ENV
    cfg.settings.ENV = "production"
    phone = "+910000000999"
    try:
        r = aioredis.from_url(cfg.settings.REDIS_URL, decode_responses=True)
        key = f"otp_rate:{phone}"
        await r.set(key, "3")  # Max out rate limit

        with pytest.raises(HTTPException) as exc:
            await check_otp_rate_limit(phone)
        assert exc.value.status_code == 429
        await r.delete(key)
        await r.aclose()
    finally:
        cfg.settings.ENV = original

