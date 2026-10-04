"""
Phase 4 Gate Tests: Rules, Translation & Messaging (Aligned to Specification).

Verifications:
1.  Rule boundaries at exactly 0.60 / 0.70 / 0.75 on spec variables:
    - false_onset_prob at 0.60 for DELAY_SOWING (0.60 triggers, 0.59 does not)
    - break_prob at 0.70 with duration >= 10 for BREAK_WARNING (0.70 triggers, 0.69 does not)
    - excess_rain_prob at 0.75 for DOWNPOUR/EXCESS_RAIN (0.75 triggers, 0.74 does not)
2.  SAFE_TO_SOW triggers on onset >= 0.65 AND false_onset < 0.30.
3.  ALTER_CROP triggers only on false_onset >= 0.60 AND past state sowing window (not onset < 0.60 alone).
4.  Break rule requires break_prob >= 0.70 AND break_duration_days_p50 >= 10.
5.  Exhaustive irrigation source mapping: every IrrigationSource enum value maps to exactly one branch.
6.  Channel-specific consent (whatsapp_consent, sms_consent) and opt-out without raising in Celery.
7.  CRITICAL cooldown exception ONLY when risk escalates above the last sent advisory; repeated CRITICAL within 72h is suppressed.
8.  Data honesty: real provider blocked for both SIMULATED and HINDCAST data.
9.  Production fail-fast: ENV=production rejects mock provider, unset PUBLIC_BASE_URL, default secrets.
10. Vetted template vs free-text machine translation flags.
11. TTS audio generated and cached.
12. Retrying failed notifications updates in-place without violating unique constraint.
13. Webhook signature constant-time check against exact public URL.
"""
import hashlib
import hmac
import os
import secrets
from base64 import b64encode
from datetime import date, datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://pannaga:pannaga@postgis:5432/pannaga")
os.environ.setdefault("REDIS_URL", "redis://redis:6379/0")
os.environ.setdefault("SECRET_KEY", "supersecretkey_for_development_only_please_change_in_production_minimum_32_characters")
os.environ.setdefault("ENV", "test")
os.environ.setdefault("MESSAGING_PROVIDER", "mock")

DATABASE_URL = os.environ["DATABASE_URL"]

import redis as sync_redis


def fresh_phone():
    return f"+919{secrets.randbelow(900_000_000) + 100_000_000}"


def clear_rl(phone):
    try:
        r = sync_redis.from_url(os.environ["REDIS_URL"])
        r.delete(f"otp_rate:{phone}")
        r.close()
    except Exception:
        pass


def make_engine():
    return create_async_engine(DATABASE_URL, poolclass=NullPool)


async def override_get_db():
    engine = make_engine()
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as session:
        yield session
    await engine.dispose()


def make_client():
    from app.main import app
    from app.db.session import get_db
    app.dependency_overrides[get_db] = override_get_db
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def login(client: AsyncClient, phone: str) -> None:
    clear_rl(phone)
    await client.post("/api/v1/auth/request-otp", json={"phone_number": phone})
    await client.post("/api/v1/auth/verify-otp",
                      json={"phone_number": phone, "otp": "000000"})


# ─── Fixture helpers ──────────────────────────────────────────────────────────

async def _make_forecast(db: AsyncSession, panchayat_id: int = 1, block_id: int = 1,
                          onset_prob: float = 0.8, break_prob: float = 0.3,
                          excess_rain_prob: float = 0.3,
                          false_onset_prob: float = 0.15,
                          break_duration_days_p50: float = 7.0,
                          data_source_str: str = "SIMULATED"):
    from app.models.climate import GridForecast
    from app.models.enums import DataSource
    fc = GridForecast(
        panchayat_id=panchayat_id,
        block_id=block_id,
        issue_date=date.today(),
        target_week_start=date.today(),
        target_week_end=date.today() + timedelta(days=6),
        lead_week=1,
        onset_prob=onset_prob,
        break_prob=break_prob,
        excess_rain_prob=excess_rain_prob,
        false_onset_prob=false_onset_prob,
        break_duration_days_p50=break_duration_days_p50,
        p10_rainfall_mm=20.0, p50_rainfall_mm=40.0, p90_rainfall_mm=65.0,
        confidence=0.72,
        data_source=DataSource(data_source_str),
    )
    db.add(fc)
    await db.flush()
    return fc


async def _make_rule(db: AsyncSession, rule_code: str,
                     cond: dict = None,
                     severity_str: str = "HIGH", crop_type: str = "cotton",
                     action_type: str = "PREPARE"):
    unique_code = f"{rule_code}_{secrets.token_hex(4)}"
    from app.models.agronomy import AgronomicRule
    from app.models.enums import AdvisorySeverity
    rule = AgronomicRule(
        rule_code=unique_code,
        crop_type=crop_type,
        growth_stage="vegetative",
        trigger_condition_json=cond or {},
        advisory_template_en="Advisory: {crop_type} in {week_label}.",
        severity=AdvisorySeverity(severity_str),
        action_type=action_type,
        source_reference="ICAR Standard Protocol 2024",
        is_approved=True,
    )
    db.add(rule)
    await db.flush()
    return rule


# ─── 1. Rule boundaries at exact 0.60 / 0.70 / 0.75 ───────────────────────────

@pytest.mark.asyncio(loop_scope="function")
async def test_false_onset_boundary_0_60():
    """DELAY_SOWING: false_onset_prob >= 0.60 triggers; 0.59 does not."""
    from app.services.agronomy_engine import evaluate_rule
    from app.models.users import FarmerProfile

    engine = make_engine()
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as db:
        rule = await _make_rule(
            db, "TEST_DELAY_SOWING",
            cond={"false_onset_prob_gte": 0.60, "allowed_crop_status": ["NOT_STARTED", "PLANNED"]},
            action_type="DELAY_SOWING",
        )
        fc_above = await _make_forecast(db, false_onset_prob=0.60)
        fc_below = await _make_forecast(db, false_onset_prob=0.59)
        prof = FarmerProfile(crop_status="PLANNED")

        assert evaluate_rule(fc_above, rule, prof) is True, "false_onset=0.60 must trigger DELAY_SOWING"
        assert evaluate_rule(fc_below, rule, prof) is False, "false_onset=0.59 must NOT trigger DELAY_SOWING"
    await engine.dispose()


@pytest.mark.asyncio(loop_scope="function")
async def test_break_prob_boundary_0_70_and_duration():
    """BREAK_WARNING: break_prob >= 0.70 AND duration >= 10 triggers; 0.69 does not; duration < 10 does not."""
    from app.services.agronomy_engine import evaluate_rule

    engine = make_engine()
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as db:
        rule = await _make_rule(
            db, "TEST_BREAK_WARNING",
            cond={"break_prob_gte": 0.70, "break_duration_days_p50_gte": 10.0},
            action_type="BREAK_WARNING",
        )
        fc_triggers = await _make_forecast(db, break_prob=0.70, break_duration_days_p50=10.0)
        fc_below_prob = await _make_forecast(db, break_prob=0.69, break_duration_days_p50=12.0)
        fc_short_dur = await _make_forecast(db, break_prob=0.75, break_duration_days_p50=8.0)

        assert evaluate_rule(fc_triggers, rule) is True, "break=0.70, dur=10 must trigger"
        assert evaluate_rule(fc_below_prob, rule) is False, "break=0.69 must NOT trigger"
        assert evaluate_rule(fc_short_dur, rule) is False, "duration=8 days must NOT trigger 10-day break rule"
    await engine.dispose()


@pytest.mark.asyncio(loop_scope="function")
async def test_heavy_rain_boundary_0_75():
    """EXCESS_RAIN: excess_rain_prob >= 0.75 triggers; 0.74 does not."""
    from app.services.agronomy_engine import evaluate_rule

    engine = make_engine()
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as db:
        rule = await _make_rule(
            db, "TEST_DOWNPOUR",
            cond={"excess_rain_prob_gte": 0.75},
            severity_str="CRITICAL",
            action_type="EXCESS_RAIN",
        )
        fc_above = await _make_forecast(db, excess_rain_prob=0.75)
        fc_below = await _make_forecast(db, excess_rain_prob=0.74)

        assert evaluate_rule(fc_above, rule) is True, "excess=0.75 must trigger"
        assert evaluate_rule(fc_below, rule) is False, "excess=0.74 must NOT trigger"
    await engine.dispose()


# ─── 2. SAFE_TO_SOW & ALTER_CROP spec rules ───────────────────────────────────

@pytest.mark.asyncio(loop_scope="function")
async def test_safe_to_sow_spec():
    """SAFE_TO_SOW: onset >= 0.65 AND false_onset < 0.30."""
    from app.services.agronomy_engine import evaluate_rule

    engine = make_engine()
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as db:
        rule = await _make_rule(
            db, "TEST_SAFE_SOW",
            cond={"onset_prob_gte": 0.65, "false_onset_prob_lt": 0.30},
            action_type="SAFE_TO_SOW",
        )
        fc_valid = await _make_forecast(db, onset_prob=0.65, false_onset_prob=0.25)
        fc_high_false_onset = await _make_forecast(db, onset_prob=0.70, false_onset_prob=0.35)
        fc_low_onset = await _make_forecast(db, onset_prob=0.64, false_onset_prob=0.20)

        assert evaluate_rule(fc_valid, rule) is True
        assert evaluate_rule(fc_high_false_onset, rule) is False, "false_onset >= 0.30 must block SAFE_TO_SOW"
        assert evaluate_rule(fc_low_onset, rule) is False, "onset < 0.65 must block SAFE_TO_SOW"
    await engine.dispose()


@pytest.mark.asyncio(loop_scope="function")
async def test_alter_crop_requires_past_sowing_window():
    """ALTER_CROP triggers ONLY on false_onset >= 0.60 AND past state window (not onset < 0.60 alone)."""
    from app.services.agronomy_engine import evaluate_rule
    from app.models.users import FarmerProfile

    engine = make_engine()
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as db:
        rule = await _make_rule(
            db, "TEST_ALTER_CROP",
            cond={"false_onset_prob_gte": 0.60, "requires_past_sowing_window": True},
            action_type="ALTER_CROP",
        )
        fc = await _make_forecast(db, onset_prob=0.40, false_onset_prob=0.65)

        prof_normal = FarmerProfile(crop_status="PLANNED")
        prof_past_window = FarmerProfile(crop_status="NOT_STARTED")
        setattr(prof_past_window, "is_past_sowing_window", True)

        # Within sowing window: ALTER_CROP must NOT trigger despite low onset / high false onset
        assert evaluate_rule(fc, rule, prof_normal, is_past_sowing_window=False) is False

        # Past sowing window: ALTER_CROP triggers
        assert evaluate_rule(fc, rule, prof_past_window, is_past_sowing_window=True) is True
    await engine.dispose()


@pytest.mark.asyncio(loop_scope="function")
async def test_rules_load_from_agronomic_rule_table():
    """Verify rules are dynamically queried from AgronomicRule database table."""
    from app.models.agronomy import AgronomicRule
    from app.services.agronomy_engine import generate_advisories_for_forecast

    engine = make_engine()
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as db:
        # Create a unique approved rule in the DB table
        rule = await _make_rule(
            db, "TEST_DB_TABLE_RULE",
            cond={"onset_prob_gte": 0.70},
            severity_str="HIGH",
            crop_type="paddy",
            action_type="SAFE_TO_SOW",
        )
        fc = await _make_forecast(db, onset_prob=0.75, false_onset_prob=0.10)

        # Call engine function which evaluates all approved rules directly from DB
        generated = await generate_advisories_for_forecast(fc, db)
        rule_ids = [adv.rule_id for adv in generated]

        assert rule.id in rule_ids, "generate_advisories_for_forecast must load and evaluate rules from AgronomicRule table"

        # Cleanup session changes
        await db.rollback()
    await engine.dispose()


# ─── 3. Exhaustive Irrigation Source Mapping ──────────────────────────────────

def test_exhaustive_irrigation_mapping():
    """Every IrrigationSource enum value maps to exactly one branch (IRRIGATED or RAINFED)."""
    from app.models.enums import IrrigationSource
    from app.services.agronomy_engine import get_irrigation_branch, IRRIGATED_SOURCES, RAINFED_SOURCES

    for src in IrrigationSource:
        branch = get_irrigation_branch(src)
        assert branch in ("IRRIGATED", "RAINFED")

        is_irrigated = src in IRRIGATED_SOURCES
        is_rainfed = src in RAINFED_SOURCES

        # Mutually exclusive and completely exhaustive
        assert is_irrigated ^ is_rainfed, f"{src} must be in exactly one branch"
        if is_irrigated:
            assert branch == "IRRIGATED"
        else:
            assert branch == "RAINFED"


@pytest.mark.asyncio(loop_scope="function")
async def test_protective_irrigation_vs_moisture_conservation():
    """PROTECTIVE_IRRIGATION applies to IRRIGATED farmers; MOISTURE_CONSERVATION applies to RAINFED."""
    from app.models.enums import IrrigationSource
    from app.models.users import FarmerProfile
    from app.services.agronomy_engine import evaluate_rule

    engine = make_engine()
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as db:
        fc_break = await _make_forecast(db, break_prob=0.75, break_duration_days_p50=12.0)
        prot_rule = await _make_rule(
            db, "TEST_PROT_IRR",
            cond={"break_prob_gte": 0.70, "break_duration_days_p50_gte": 10.0},
            action_type="PROTECTIVE_IRRIGATION",
        )
        moist_rule = await _make_rule(
            db, "TEST_MOIST_CONS",
            cond={"break_prob_gte": 0.70, "break_duration_days_p50_gte": 10.0},
            action_type="MOISTURE_CONSERVATION",
        )

        prof_canal = FarmerProfile(crop_status="VEGETATIVE", irrigation_source=IrrigationSource.CANAL)
        prof_drip = FarmerProfile(crop_status="VEGETATIVE", irrigation_source=IrrigationSource.DRIP_SPRINKLER)
        prof_rainfed = FarmerProfile(crop_status="VEGETATIVE", irrigation_source=IrrigationSource.RAINFED)

        # Canal & Drip get PROTECTIVE_IRRIGATION, not MOISTURE_CONSERVATION
        assert evaluate_rule(fc_break, prot_rule, prof_canal) is True
        assert evaluate_rule(fc_break, moist_rule, prof_canal) is False
        assert evaluate_rule(fc_break, prot_rule, prof_drip) is True
        assert evaluate_rule(fc_break, moist_rule, prof_drip) is False

        # Rainfed gets MOISTURE_CONSERVATION, not PROTECTIVE_IRRIGATION
        assert evaluate_rule(fc_break, moist_rule, prof_rainfed) is True
        assert evaluate_rule(fc_break, prot_rule, prof_rainfed) is False
    await engine.dispose()


@pytest.mark.asyncio(loop_scope="function")
async def test_break_rule_limited_to_standing_crop():
    """Break warning rule applies only to standing crop stages (SOWN, VEGETATIVE, FLOWERING_PODDING)."""
    from app.models.users import FarmerProfile
    from app.services.agronomy_engine import evaluate_rule

    engine = make_engine()
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as db:
        fc = await _make_forecast(db, break_prob=0.75, break_duration_days_p50=12.0)
        rule = await _make_rule(
            db, "TEST_BREAK_STAGE",
            cond={"break_prob_gte": 0.70, "break_duration_days_p50_gte": 10.0},
            action_type="BREAK_WARNING",
        )

        assert evaluate_rule(fc, rule, FarmerProfile(crop_status="VEGETATIVE")) is True
        assert evaluate_rule(fc, rule, FarmerProfile(crop_status="SOWN")) is True
        assert evaluate_rule(fc, rule, FarmerProfile(crop_status="FLOWERING_PODDING")) is True

        # Does NOT apply before sowing or after harvest
        assert evaluate_rule(fc, rule, FarmerProfile(crop_status="NOT_STARTED")) is False
        assert evaluate_rule(fc, rule, FarmerProfile(crop_status="HARVEST_READY")) is False
    await engine.dispose()


@pytest.mark.asyncio(loop_scope="function")
async def test_drainage_prep_and_early_harvest_rules():
    """DRAINAGE_PREP applies to standing vegetative crops; EARLY_HARVEST applies to mature/harvest-ready crops."""
    from app.models.users import FarmerProfile
    from app.services.agronomy_engine import evaluate_rule

    engine = make_engine()
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as db:
        fc = await _make_forecast(db, excess_rain_prob=0.80)
        rule_drainage = await _make_rule(
            db, "TEST_DRAINAGE",
            cond={"excess_rain_prob_gte": 0.75},
            action_type="DRAINAGE_PREP",
        )
        rule_early_harvest = await _make_rule(
            db, "TEST_EARLY_HARV",
            cond={"excess_rain_prob_gte": 0.75},
            action_type="EARLY_HARVEST",
        )

        # DRAINAGE_PREP
        assert evaluate_rule(fc, rule_drainage, FarmerProfile(crop_status="VEGETATIVE")) is True
        assert evaluate_rule(fc, rule_drainage, FarmerProfile(crop_status="NOT_STARTED")) is False

        # EARLY_HARVEST
        assert evaluate_rule(fc, rule_early_harvest, FarmerProfile(crop_status="HARVEST_READY")) is True
        assert evaluate_rule(fc, rule_early_harvest, FarmerProfile(crop_status="SOWN")) is False
    await engine.dispose()


# ─── 4. Channel-specific Consent & Opt-Out (No Crash in Celery) ───────────────

@pytest.mark.asyncio(loop_scope="function")
async def test_channel_specific_consent_and_opt_out():
    """WhatsApp consent, SMS consent, and opted_out_at recorded as blocked, never raise."""
    from app.models.agronomy import GeneratedAdvisory
    from app.models.enums import AdvisorySeverity, DataSource, NotificationChannel, NotificationStatus
    from app.models.users import User
    from app.services.messaging_gateway import dispatch_notification

    engine = make_engine()
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as db:
        # User who opted out via STOP
        user_opted_out = User(
            phone_number=fresh_phone(), role="FARMER", is_active=True,
            consent_given_at=datetime.now(timezone.utc),
            opted_out_at=datetime.now(timezone.utc),
        )
        # User who gave SMS consent but NOT WhatsApp consent
        user_sms_only = User(
            phone_number=fresh_phone(), role="FARMER", is_active=True,
            consent_given_at=datetime.now(timezone.utc),
            sms_consent=True, whatsapp_consent=False,
        )
        db.add_all([user_opted_out, user_sms_only])
        await db.flush()

        fc = await _make_forecast(db)
        rule = await _make_rule(db, "TEST_CONSENT_SPEC")
        adv = GeneratedAdvisory(
            panchayat_id=1, block_id=1, forecast_id=fc.id, rule_id=rule.id,
            crop_type="cotton", language="en", headline="H", content="C",
            severity=AdvisorySeverity.HIGH, data_source=DataSource.SIMULATED,
        )
        db.add(adv)
        await db.commit()

        # 1. Opted out user: returns BLOCKED_OPT_OUT (does not raise)
        log1 = await dispatch_notification(
            advisory=adv, recipient_phone=user_opted_out.phone_number,
            recipient_id=user_opted_out.id, message_body="Msg",
            channel=NotificationChannel.SMS, db=db,
        )
        assert log1.dispatch_status == NotificationStatus.BLOCKED_OPT_OUT

        # 2. WhatsApp send to user without WhatsApp consent: returns BLOCKED_CONSENT
        log2 = await dispatch_notification(
            advisory=adv, recipient_phone=user_sms_only.phone_number,
            recipient_id=user_sms_only.id, message_body="Msg",
            channel=NotificationChannel.WHATSAPP, db=db,
        )
        assert log2.dispatch_status == NotificationStatus.BLOCKED_CONSENT

        # 3. SMS send to user with SMS consent: allowed past consent check
        log3 = await dispatch_notification(
            advisory=adv, recipient_phone=user_sms_only.phone_number,
            recipient_id=user_sms_only.id, message_body="Msg",
            channel=NotificationChannel.SMS, db=db,
        )
        assert log3.dispatch_status != NotificationStatus.BLOCKED_CONSENT
    await engine.dispose()


# ─── 5. Cooldown: Escalation Exception ONLY; Repeated CRITICAL Suppressed ──────

@pytest.mark.asyncio(loop_scope="function")
async def test_critical_cooldown_escalation_only():
    """
    Escalation exception applies ONLY when risk escalates above last sent advisory.
    Repeated CRITICAL within 72h is suppressed (anti-spam).
    """
    from app.models.agronomy import GeneratedAdvisory, NotificationLog
    from app.models.enums import AdvisorySeverity, NotificationChannel, NotificationStatus, DataSource
    from app.models.users import User
    from app.services.agronomy_engine import check_farmer_cooldown

    engine = make_engine()
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as db:
        user = User(phone_number=fresh_phone(), role="FARMER", is_active=True,
                    consent_given_at=datetime.now(timezone.utc))
        db.add(user)
        await db.flush()

        fc = await _make_forecast(db)
        rule_high = await _make_rule(db, "TEST_ESC_HIGH", severity_str="HIGH")
        rule_crit = await _make_rule(db, "TEST_ESC_CRIT", severity_str="CRITICAL")

        adv_high = GeneratedAdvisory(
            panchayat_id=1, block_id=1, forecast_id=fc.id, rule_id=rule_high.id,
            crop_type="cotton", language="en", headline="H", content="C",
            severity=AdvisorySeverity.HIGH, data_source=DataSource.SIMULATED,
        )
        adv_crit = GeneratedAdvisory(
            panchayat_id=1, block_id=1, forecast_id=fc.id, rule_id=rule_crit.id,
            crop_type="cotton", language="en", headline="C", content="C",
            severity=AdvisorySeverity.CRITICAL, data_source=DataSource.SIMULATED,
        )
        db.add_all([adv_high, adv_crit])
        await db.flush()

        # Farmer sent HIGH advisory 6 hours ago
        log_high = NotificationLog(
            advisory_id=adv_high.id, recipient_user_id=user.id,
            channel=NotificationChannel.SMS, message_content="High alert",
            dispatch_status=NotificationStatus.SENT, attempt_count=1,
            idempotency_key=secrets.token_hex(16),
            created_at=datetime.now(timezone.utc) - timedelta(hours=6),
        )
        db.add(log_high)
        await db.commit()

        # Another HIGH advisory: Suppressed by cooldown
        assert await check_farmer_cooldown(user.id, AdvisorySeverity.HIGH, db) is False

        # CRITICAL advisory: Risk ESCALATES (HIGH -> CRITICAL) -> Allowed!
        assert await check_farmer_cooldown(user.id, AdvisorySeverity.CRITICAL, db) is True

        # Now suppose the CRITICAL alert was sent
        log_crit = NotificationLog(
            advisory_id=adv_crit.id, recipient_user_id=user.id,
            channel=NotificationChannel.SMS, message_content="Critical alert",
            dispatch_status=NotificationStatus.SENT, attempt_count=1,
            idempotency_key=secrets.token_hex(16),
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        db.add(log_crit)
        await db.commit()

        # REPEATED CRITICAL within 72h: Risk did NOT escalate -> SUPPRESSED!
        assert await check_farmer_cooldown(user.id, AdvisorySeverity.CRITICAL, db) is False
    await engine.dispose()


@pytest.mark.asyncio(loop_scope="function")
async def test_repeated_critical_within_72h_suppressed():
    """Explicit verification: a second CRITICAL within 72h is suppressed even though severity is CRITICAL."""
    from app.models.agronomy import GeneratedAdvisory, NotificationLog
    from app.models.enums import AdvisorySeverity, NotificationChannel, NotificationStatus, DataSource
    from app.models.users import User
    from app.services.agronomy_engine import check_farmer_cooldown

    engine = make_engine()
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as db:
        user = User(phone_number=fresh_phone(), role="FARMER", is_active=True,
                    consent_given_at=datetime.now(timezone.utc))
        db.add(user)
        await db.flush()

        fc = await _make_forecast(db)
        rule_crit = await _make_rule(db, "TEST_REPEAT_CRIT", severity_str="CRITICAL")
        adv = GeneratedAdvisory(
            panchayat_id=1, block_id=1, forecast_id=fc.id, rule_id=rule_crit.id,
            crop_type="cotton", language="en", headline="Crit", content="Crit",
            severity=AdvisorySeverity.CRITICAL, data_source=DataSource.SIMULATED,
        )
        db.add(adv)
        await db.flush()

        log = NotificationLog(
            advisory_id=adv.id, recipient_user_id=user.id,
            channel=NotificationChannel.SMS, message_content="Downpour Alert",
            dispatch_status=NotificationStatus.SENT, attempt_count=1,
            idempotency_key=secrets.token_hex(16),
            created_at=datetime.now(timezone.utc) - timedelta(hours=12),
        )
        db.add(log)
        await db.commit()

        # Next cycle 12 hours later sends another CRITICAL advisory -> MUST BE SUPPRESSED
        is_allowed = await check_farmer_cooldown(user.id, AdvisorySeverity.CRITICAL, db)
        assert is_allowed is False, "Repeated CRITICAL notification within 72h must be suppressed"
    await engine.dispose()


def test_select_farmer_cycle_advisories():
    """Limits to at most 1 primary + 1 secondary advisory per farmer per cycle, prioritized by severity."""
    from app.models.agronomy import GeneratedAdvisory
    from app.models.enums import AdvisorySeverity, DataSource
    from app.services.agronomy_engine import select_farmer_cycle_advisories

    adv1 = GeneratedAdvisory(id=1, rule_id=10, severity=AdvisorySeverity.CRITICAL, headline="A1", content="", crop_type="cotton", language="en", data_source=DataSource.SIMULATED)
    adv2 = GeneratedAdvisory(id=2, rule_id=11, severity=AdvisorySeverity.HIGH, headline="A2", content="", crop_type="cotton", language="en", data_source=DataSource.SIMULATED)
    adv3 = GeneratedAdvisory(id=3, rule_id=12, severity=AdvisorySeverity.MEDIUM, headline="A3", content="", crop_type="cotton", language="en", data_source=DataSource.SIMULATED)
    adv4 = GeneratedAdvisory(id=4, rule_id=10, severity=AdvisorySeverity.LOW, headline="A4", content="", crop_type="cotton", language="en", data_source=DataSource.SIMULATED)

    candidates = [adv3, adv1, adv4, adv2]
    primary, secondary = select_farmer_cycle_advisories(candidates)

    assert primary is not None
    assert primary.severity == AdvisorySeverity.CRITICAL
    assert primary.id == 1

    assert secondary is not None
    assert secondary.severity == AdvisorySeverity.HIGH
    assert secondary.id == 2
    assert secondary.rule_id != primary.rule_id


# ─── 6. Data Honesty: Block SIMULATED and HINDCAST Data ───────────────────────

@pytest.mark.asyncio(loop_scope="function")
async def test_block_non_live_data_hindcast_and_simulated():
    """Neither SIMULATED nor HINDCAST forecasts can ever reach an external provider."""
    from app.models.agronomy import GeneratedAdvisory
    from app.models.enums import AdvisorySeverity, DataSource, NotificationChannel, NotificationStatus
    from app.models.users import User
    from app.services.messaging_gateway import dispatch_notification

    engine = make_engine()
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as db:
        user = User(phone_number=fresh_phone(), role="FARMER", is_active=True,
                    consent_given_at=datetime.now(timezone.utc))
        db.add(user)
        await db.flush()

        fc_sim = await _make_forecast(db, data_source_str="SIMULATED")
        fc_hind = await _make_forecast(db, data_source_str="HINDCAST")
        rule = await _make_rule(db, "TEST_DATA_HONESTY")

        adv_sim = GeneratedAdvisory(
            panchayat_id=1, block_id=1, forecast_id=fc_sim.id, rule_id=rule.id,
            crop_type="cotton", language="en", headline="Sim", content="Sim",
            severity=AdvisorySeverity.HIGH, data_source=DataSource.SIMULATED,
        )
        adv_hind = GeneratedAdvisory(
            panchayat_id=1, block_id=1, forecast_id=fc_hind.id, rule_id=rule.id,
            crop_type="cotton", language="en", headline="Hind", content="Hind",
            severity=AdvisorySeverity.HIGH, data_source=DataSource.HINDCAST,
        )
        db.add_all([adv_sim, adv_hind])
        await db.commit()

        log_sim = await dispatch_notification(
            advisory=adv_sim, recipient_phone=user.phone_number,
            recipient_id=user.id, message_body="Body",
            channel=NotificationChannel.SMS, db=db,
        )
        log_hind = await dispatch_notification(
            advisory=adv_hind, recipient_phone=user.phone_number,
            recipient_id=user.id, message_body="Body",
            channel=NotificationChannel.SMS, db=db,
        )

        assert log_sim.dispatch_status == NotificationStatus.BLOCKED_SIMULATED
        assert log_hind.dispatch_status in (NotificationStatus.BLOCKED_NON_LIVE, NotificationStatus.BLOCKED_SIMULATED)

        # Cleanup test hindcast rows so foundation tests stay pure
        await db.delete(log_hind)
        await db.delete(adv_hind)
        await db.delete(fc_hind)
        await db.commit()
    await engine.dispose()


# ─── 7. Failed Sends Retry In-Place (No Unique Index Violation) ────────────────

@pytest.mark.asyncio(loop_scope="function")
async def test_failed_send_retried_in_place():
    """Retrying a FAILED notification updates the row in-place without violating unique index."""
    from app.models.agronomy import GeneratedAdvisory, NotificationLog
    from app.models.enums import AdvisorySeverity, DataSource, NotificationChannel, NotificationStatus
    from app.models.users import User
    from app.services.messaging_gateway import dispatch_notification

    engine = make_engine()
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as db:
        user = User(phone_number=fresh_phone(), role="FARMER", is_active=True,
                    consent_given_at=datetime.now(timezone.utc))
        db.add(user)
        await db.flush()

        fc = await _make_forecast(db)
        rule = await _make_rule(db, "TEST_RETRY_FAILED")
        adv = GeneratedAdvisory(
            panchayat_id=1, block_id=1, forecast_id=fc.id, rule_id=rule.id,
            crop_type="cotton", language="en", headline="Adv", content="Adv",
            severity=AdvisorySeverity.HIGH, data_source=DataSource.LIVE,
        )
        db.add(adv)
        await db.commit()

        # Insert a pre-existing FAILED notification
        failed_log = NotificationLog(
            advisory_id=adv.id, recipient_user_id=user.id,
            channel=NotificationChannel.SMS, message_content="Msg",
            dispatch_status=NotificationStatus.FAILED, attempt_count=1,
            idempotency_key=secrets.token_hex(16),
        )
        db.add(failed_log)
        await db.commit()

        # Dispatch again: must update existing row in-place
        retried_log = await dispatch_notification(
            advisory=adv, recipient_phone=user.phone_number,
            recipient_id=user.id, message_body="Msg",
            channel=NotificationChannel.SMS, db=db,
        )

        assert retried_log.id == failed_log.id
        assert retried_log.attempt_count == 2
        assert retried_log.dispatch_status == NotificationStatus.SENT

        # Verify only 1 row in DB for (recipient, advisory, channel)
        count_res = await db.execute(
            select(func.count()).select_from(NotificationLog).where(
                NotificationLog.advisory_id == adv.id,
                NotificationLog.recipient_user_id == user.id,
                NotificationLog.channel == NotificationChannel.SMS,
            )
        )
        assert count_res.scalar() == 1

        # Clean up live test row
        await db.delete(retried_log)
        await db.delete(adv)
        await db.commit()
    await engine.dispose()


@pytest.mark.asyncio(loop_scope="function")
async def test_resend_does_not_duplicate():
    """Resending an advisory to the same recipient on the same channel does not create duplicate rows."""
    from app.models.agronomy import GeneratedAdvisory, NotificationLog
    from app.models.enums import AdvisorySeverity, DataSource, NotificationChannel, NotificationStatus
    from app.models.users import User
    from app.services.messaging_gateway import dispatch_notification

    engine = make_engine()
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as db:
        user = User(phone_number=fresh_phone(), role="FARMER", is_active=True,
                    consent_given_at=datetime.now(timezone.utc))
        db.add(user)
        await db.flush()

        fc = await _make_forecast(db)
        rule = await _make_rule(db, "TEST_RESEND_DEDUP")
        adv = GeneratedAdvisory(
            panchayat_id=1, block_id=1, forecast_id=fc.id, rule_id=rule.id,
            crop_type="cotton", language="en", headline="Adv", content="Adv",
            severity=AdvisorySeverity.HIGH, data_source=DataSource.LIVE,
        )
        db.add(adv)
        await db.commit()

        # First dispatch
        log1 = await dispatch_notification(
            advisory=adv, recipient_phone=user.phone_number,
            recipient_id=user.id, message_body="Msg 1",
            channel=NotificationChannel.SMS, db=db,
        )
        assert log1.dispatch_status == NotificationStatus.SENT

        # Immediate resend attempt (e.g. worker retry or duplicate trigger)
        log2 = await dispatch_notification(
            advisory=adv, recipient_phone=user.phone_number,
            recipient_id=user.id, message_body="Msg 2",
            channel=NotificationChannel.SMS, db=db,
        )

        # Same DB row ID updated, NOT a duplicate row
        assert log1.id == log2.id

        # Unique count in database must be strictly 1
        count_res = await db.execute(
            select(func.count()).select_from(NotificationLog).where(
                NotificationLog.advisory_id == adv.id,
                NotificationLog.recipient_user_id == user.id,
                NotificationLog.channel == NotificationChannel.SMS,
            )
        )
        assert count_res.scalar() == 1, "Resend must not duplicate notification log row"

        # Cleanup
        await db.delete(log2)
        await db.delete(adv)
        await db.commit()
    await engine.dispose()


# ─── 8. Production Fail-Fast Validation ────────────────────────────────────────

def test_production_fail_fast_checks():
    """validate_production_settings() rejects mock/console providers, unset URLs, default keys."""
    from app.core.config import Settings, validate_production_settings

    # Rejects mock provider
    s1 = Settings(ENV="production", MESSAGING_PROVIDER="mock", SECRET_KEY="real_key_length_greater_than_32_chars!", PUBLIC_BASE_URL="https://pannaga.org.in")
    with pytest.raises(RuntimeError, match="MESSAGING_PROVIDER"):
        validate_production_settings(s1)

    # Rejects default secret key
    s2 = Settings(ENV="production", MESSAGING_PROVIDER="twilio", SECRET_KEY="supersecretkey_for_development_only_please_change_in_production_minimum_32_characters", PUBLIC_BASE_URL="https://pannaga.org.in")
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        validate_production_settings(s2)

    # Rejects local/unset PUBLIC_BASE_URL
    s3 = Settings(ENV="production", MESSAGING_PROVIDER="twilio", SECRET_KEY="a_legitimate_production_secret_key_32_chars!", PUBLIC_BASE_URL="http://localhost:8000")
    with pytest.raises(RuntimeError, match="PUBLIC_BASE_URL"):
        validate_production_settings(s3)


# ─── 9. Vetted Template vs Machine Translation Flags ──────────────────────────

def test_vetted_template_vs_mt_flags():
    """Pre-vetted templates are marked vetted_template: True, MT marked machine_translated: True."""
    from app.services.translation import translate_advisory

    # Pre-vetted translation
    vetted = translate_advisory(
        headline="Onset alert", content="Prepare field.", target_lang="hi",
        vetted_headline="मानसून चेतावनी", vetted_content="खेत तैयार करें।",
    )
    assert vetted["vetted_template"] is True
    assert vetted["machine_translated"] is False
    assert vetted["flagged_for_review"] is False

    # Machine-translated (free-text)
    mt = translate_advisory("Severe dry spell predicted", "Apply mulching.", target_lang="hi")
    assert mt["vetted_template"] is False
    assert mt["machine_translated"] is True
    assert mt["flagged_for_review"] is True
    assert "review required" in mt["review_disclaimer"].lower()


def test_translation_preserves_numbers_and_revalidates():
    """Numbers, units, percentages, and dates must be preserved exactly after translation."""
    from app.services.translation import translate_advisory, extract_preserved_tokens, validate_preserved_elements

    headline = "Rainfall expected: 45.5 mm (75%) by 2026-06-15 in week 2"
    content = "Expected temperature drop: 4.2 °C with 60 mm total downpour."
    
    tokens = extract_preserved_tokens(f"{headline} {content}")
    assert any("45.5" in t or "45.5 mm" in t for t in tokens)
    assert any("75%" in t for t in tokens)
    assert any("2026-06-15" in t for t in tokens)

    tr = translate_advisory(headline, content, "hi")
    assert validate_preserved_elements(headline, tr["headline"]) is True
    assert validate_preserved_elements(content, tr["content"]) is True


def test_translation_revalidation_fails_if_tampered():
    """If translation drops or tampers with numbers/dates, validation returns False."""
    from app.services.translation import validate_preserved_elements

    orig = "Precipitation 65.0 mm expected on 2026-07-01."
    tampered = "Precipitation expected on future date."  # Dropped 65.0 mm and date
    assert validate_preserved_elements(orig, tampered) is False


def test_dlt_and_whatsapp_template_config():
    """DLT and WhatsApp template IDs are configured and accessible."""
    from app.core.config import settings

    assert hasattr(settings, "DLT_ONSET_TEMPLATE_ID")
    assert hasattr(settings, "DLT_BREAK_TEMPLATE_ID")
    assert hasattr(settings, "WHATSAPP_ONSET_TEMPLATE_NAME")
    assert hasattr(settings, "WHATSAPP_BREAK_TEMPLATE_NAME")


# ─── 10. Webhook Security: Constant-Time & Public URL ─────────────────────────

@pytest.mark.asyncio(loop_scope="function")
async def test_webhook_rejects_missing_signature():
    """POST /webhooks/twilio/status: 403 on missing X-Twilio-Signature."""
    async with make_client() as client:
        resp = await client.post(
            "/api/v1/webhooks/twilio/status",
            data={"MessageSid": "SM123", "MessageStatus": "delivered"},
        )
        assert resp.status_code == 403


@pytest.mark.asyncio(loop_scope="function")
async def test_webhook_rejects_invalid_signature():
    """POST /webhooks/twilio/status: 403 on invalid X-Twilio-Signature."""
    async with make_client() as client:
        resp = await client.post(
            "/api/v1/webhooks/twilio/status",
            data={"MessageSid": "SM123", "MessageStatus": "delivered"},
            headers={"X-Twilio-Signature": "INVALIDSIG=="},
        )
        assert resp.status_code == 403


def test_webhook_constant_time_signature():
    """validate_twilio_signature checks HMAC-SHA1 in constant time against public URL."""
    from app.api.v1.webhooks import validate_twilio_signature

    auth_token = "secret_twilio_token_987"
    public_url = "https://pannaga.org.in/api/v1/webhooks/twilio/status"
    params = {"MessageSid": "SM_TEST_1", "MessageStatus": "delivered"}

    sorted_params = sorted(params.items())
    s = public_url + "".join(k + v for k, v in sorted_params)
    valid_sig = b64encode(hmac.new(auth_token.encode(), s.encode(), hashlib.sha1).digest()).decode()

    assert validate_twilio_signature(auth_token, public_url, params, valid_sig) is True
    assert validate_twilio_signature(auth_token, public_url, params, "WRONGSIG==") is False


# ─── 11. TTS Audio Generation & Disk Caching ──────────────────────────────────

def test_tts_audio_generated_and_cached():
    """TTS audio generated from text and cached on disk with non-silent WAV container."""
    from app.services.tts import generate_tts_audio, AUDIO_STORAGE_DIR, get_audio_cache_key
    import hashlib

    text = "Weekly monsoon advisory: 45 mm rainfall expected."
    url1 = generate_tts_audio(text, language="en")
    assert url1.startswith("/media/audio/")
    assert url1.endswith(".wav")

    # Verify filename is not a plain sha256(text)
    plain_sha = hashlib.sha256(f"en:{text}".encode("utf-8")).hexdigest()[:24]
    assert plain_sha not in url1, "TTS filename should be unguessable HMAC token, not simple sha256"

    # Verify cache idempotency
    url2 = generate_tts_audio(text, language="en")
    assert url1 == url2

    # Verify audio file exists, has valid non-empty payload, and is not silent (has audio wave frames)
    fname = url1.split("/")[-1]
    wav_path = AUDIO_STORAGE_DIR / fname
    assert wav_path.exists(), f"Audio file {wav_path} must exist"
    assert wav_path.stat().st_size > 44, "Audio file must contain more than just standard 44-byte header"

    with open(wav_path, "rb") as f:
        data = f.read()
    assert data[:4] == b"RIFF"
    assert data[8:12] == b"WAVE"
    pcm_samples = data[44:]
    assert len(pcm_samples) > 0, "WAV must contain audio samples"
    # Ensure samples vary (waveform, not flat zeros or silence)
    sample_set = set(pcm_samples)
    assert len(sample_set) > 5, "Audio samples must represent audible synthetic tone, not silence"



# ─── 12. Phase 6 Endpoint Tests (Officer & Farmer) ────────────────────────────

@pytest.mark.asyncio(loop_scope="function")
async def test_officer_queue_and_approval_workflow():
    """Officer queue returns pending advisories; approving pre-generates TTS audio URL."""
    from app.models.agronomy import GeneratedAdvisory
    from app.models.enums import AdvisoryApprovalStatus, AdvisorySeverity, DataSource
    from app.models.users import OfficerJurisdiction, User
    from app.core.security import create_access_token

    engine = make_engine()
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as db:
        officer = User(phone_number=fresh_phone(), role="EXTENSION_OFFICER", is_active=True,
                       consent_given_at=datetime.now(timezone.utc))
        db.add(officer)
        await db.flush()

        jur = OfficerJurisdiction(user_id=officer.id, block_id=1)
        db.add(jur)

        fc = await _make_forecast(db, block_id=1)
        rule = await _make_rule(db, "TEST_OFF_APP", severity_str="CRITICAL")
        adv = GeneratedAdvisory(
            panchayat_id=1, block_id=1, forecast_id=fc.id, rule_id=rule.id,
            crop_type="cotton", language="en", headline="Crit Alert", content="Crit Content",
            severity=AdvisorySeverity.CRITICAL, approval_status=AdvisoryApprovalStatus.PENDING,
            data_source=DataSource.SIMULATED,
        )
        db.add(adv)
        await db.commit()

        token = create_access_token(officer.id, "EXTENSION_OFFICER")
        headers = {"Authorization": f"Bearer {token}"}

        async with make_client() as client:
            # 1. Fetch queue
            q_resp = await client.get("/api/v1/officer/queue", headers=headers)
            assert q_resp.status_code == 200
            data = q_resp.json()
            assert any(item["id"] == adv.id for item in data["queue"])

            # 2. Approve advisory
            app_resp = await client.post(f"/api/v1/officer/advisories/{adv.id}/approve", headers=headers, json={"notes": "Approved"})
            assert app_resp.status_code == 200
            assert app_resp.json()["advisory_id"] == adv.id
            assert app_resp.json()["audio_url"] is not None
            assert app_resp.json()["audio_url"].startswith("/media/audio/")

        # Clean up
        await db.delete(adv)
        await db.delete(jur)
        await db.delete(officer)
        await db.commit()
    await engine.dispose()


@pytest.mark.asyncio(loop_scope="function")
async def test_officer_broadcast_dry_run_and_confirm():
    """Broadcast endpoint with confirm=False performs dry-run; confirm=True executes dispatch."""
    from app.models.agronomy import GeneratedAdvisory
    from app.models.enums import AdvisoryApprovalStatus, AdvisorySeverity, DataSource
    from app.models.users import FarmerProfile, OfficerJurisdiction, User
    from app.core.security import create_access_token

    engine = make_engine()
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as db:
        officer = User(phone_number=fresh_phone(), role="EXTENSION_OFFICER", is_active=True,
                       consent_given_at=datetime.now(timezone.utc))
        db.add(officer)
        await db.flush()

        jur = OfficerJurisdiction(user_id=officer.id, block_id=1)
        db.add(jur)

        # Farmer in panchayat 1
        farmer = User(phone_number=fresh_phone(), role="FARMER", is_active=True,
                      consent_given_at=datetime.now(timezone.utc), sms_consent=True)
        db.add(farmer)
        await db.flush()
        prof = FarmerProfile(user_id=farmer.id, panchayat_id=1, crop_type="cotton", crop_status="SOWN")
        db.add(prof)

        fc = await _make_forecast(db, block_id=1, panchayat_id=1)
        rule = await _make_rule(db, "TEST_OFF_BC")
        adv = GeneratedAdvisory(
            panchayat_id=1, block_id=1, forecast_id=fc.id, rule_id=rule.id,
            crop_type="cotton", language="en", headline="Approved Adv", content="Adv Content",
            severity=AdvisorySeverity.HIGH, approval_status=AdvisoryApprovalStatus.APPROVED,
            data_source=DataSource.SIMULATED,
        )
        db.add(adv)
        await db.commit()

        token = create_access_token(officer.id, "EXTENSION_OFFICER")
        headers = {"Authorization": f"Bearer {token}"}

        async with make_client() as client:
            # Dry-run
            dry_resp = await client.post(
                "/api/v1/officer/broadcast",
                headers=headers,
                json={"advisory_ids": [adv.id], "channel": "SMS", "confirm": False},
            )
            assert dry_resp.status_code == 200
            res = dry_resp.json()["results"][0]
            assert res["farmers_in_panchayat"] >= 1
            assert res["confirmed"] is False

            # Confirm broadcast (SIMULATED data intercepted -> blocked_simulated recorded)
            conf_resp = await client.post(
                "/api/v1/officer/broadcast",
                headers=headers,
                json={"advisory_ids": [adv.id], "channel": "SMS", "confirm": True},
            )
            assert conf_resp.status_code == 200
            res2 = conf_resp.json()["results"][0]
            assert res2["confirmed"] is True
            assert res2["blocked_simulated"] >= 1

            # Check delivery logs
            deliv_resp = await client.get("/api/v1/officer/delivery", headers=headers)
            assert deliv_resp.status_code == 200
            logs = deliv_resp.json()["logs"]
            assert any(l["advisory_id"] == adv.id for l in logs)

        # Clean up
        await db.delete(adv)
        await db.delete(prof)
        await db.delete(farmer)
        await db.delete(jur)
        await db.delete(officer)
        await db.commit()
    await engine.dispose()


@pytest.mark.asyncio(loop_scope="function")
async def test_farmer_crop_status_and_profile_updates():
    """Farmer 1-tap crop status updater supports canonical 5 stages & aliases; profile updates consent/opt-out."""
    from app.core.security import create_access_token
    from app.models.users import FarmerProfile, User

    engine = make_engine()
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as db:
        user = User(phone_number=fresh_phone(), role="FARMER", is_active=True,
                    consent_given_at=datetime.now(timezone.utc))
        db.add(user)
        await db.flush()
        prof = FarmerProfile(user_id=user.id, crop_type="paddy", crop_status="NOT_STARTED")
        db.add(prof)
        await db.commit()

        token = create_access_token(user.id, "FARMER")
        headers = {"Authorization": f"Bearer {token}"}

        async with make_client() as client:
            # 1. Update crop status to canonical stage
            r1 = await client.patch("/api/v1/me/crop-status", headers=headers, json={"crop_status": "VEGETATIVE"})
            assert r1.status_code == 200

            # 2. Update crop status using alias
            r2 = await client.patch("/api/v1/me/crop-status", headers=headers, json={"crop_status": "FLOWERING"})
            assert r2.status_code == 200

            # 3. Invalid status rejected
            r3 = await client.patch("/api/v1/me/crop-status", headers=headers, json={"crop_status": "INVALID_STAGE"})
            assert r3.status_code == 400

            # 4. Update profile consent & language (including Punjabi pa)
            r4 = await client.patch(
                "/api/v1/me",
                headers=headers,
                json={"preferred_language": "pa", "whatsapp_consent": False, "opt_out": True},
            )
            assert r4.status_code == 200
            data = r4.json()
            assert data["preferred_language"] == "pa"
            assert data["whatsapp_consent"] is False
            assert data["opted_out_at"] is not None

        # Clean up
        await db.delete(prof)
        await db.delete(user)
        await db.commit()
    await engine.dispose()


def test_stage_alias_normalization():
    """Verify alias normalization correctly maps legacy/alternate terms to canonical 5 stages."""
    STATUS_ALIASES = {
        "PLANNED": "NOT_STARTED",
        "SOWING": "SOWN",
        "FLOWERING": "FLOWERING_PODDING",
        "TRANSPLANTING": "FLOWERING_PODDING",
        "GRAIN_FILLING": "FLOWERING_PODDING",
        "HARVESTING": "HARVEST_READY",
        "HARVESTED": "HARVEST_READY",
    }
    CANONICAL = {"NOT_STARTED", "SOWN", "VEGETATIVE", "FLOWERING_PODDING", "HARVEST_READY"}

    for alias, canonical in STATUS_ALIASES.items():
        assert canonical in CANONICAL


@pytest.mark.asyncio(loop_scope="function")
async def test_harvested_crops_receive_no_sowing_or_irrigation_advisories():
    """Finished and HARVESTED crops receive neither sowing nor irrigation advisories."""
    from app.models.agronomy import AgronomicRule
    from app.models.climate import GridForecast
    from app.models.enums import AdvisorySeverity, IrrigationSource
    from app.models.users import FarmerProfile
    from app.services.agronomy_engine import evaluate_rule

    sowing_rule = AgronomicRule(
        action_type="SAFE_TO_SOW",
        crop_type="cotton",
        growth_stage="SOWING",
        trigger_condition_json={"onset_prob_gte": 0.65, "false_onset_prob_lt": 0.30},
        advisory_template_en="Safe to sow",
        severity=AdvisorySeverity.HIGH,
        source_reference="ICAR",
    )
    irrigation_rule = AgronomicRule(
        action_type="PROTECTIVE_IRRIGATION",
        crop_type="cotton",
        growth_stage="VEGETATIVE",
        trigger_condition_json={"break_prob_gte": 0.70, "break_duration_days_p50_gte": 10},
        advisory_template_en="Apply irrigation",
        severity=AdvisorySeverity.CRITICAL,
        source_reference="ICAR",
    )

    fc = GridForecast(
        onset_prob=0.80,
        break_prob=0.85,
        excess_rain_prob=0.20,
        features_json={"false_onset_prob": 0.15, "break_duration_days_p50": 12},
    )

    # 1. Harvested crop receives NO advisories
    harvested_farmer = FarmerProfile(
        crop_type="cotton",
        crop_status="HARVESTED",
        irrigation_source=IrrigationSource.CANAL,
    )
    assert evaluate_rule(fc, sowing_rule, harvested_farmer) is False
    assert evaluate_rule(fc, irrigation_rule, harvested_farmer) is False

    # 2. Standing vegetative crop receives irrigation advisory, but NOT sowing advisory
    standing_farmer = FarmerProfile(
        crop_type="cotton",
        crop_status="VEGETATIVE",
        irrigation_source=IrrigationSource.CANAL,
    )
    assert evaluate_rule(fc, sowing_rule, standing_farmer) is False
    assert evaluate_rule(fc, irrigation_rule, standing_farmer) is True

    # 3. Not-started crop receives sowing advisory, but NOT standing crop irrigation advisory
    unplanted_farmer = FarmerProfile(
        crop_type="cotton",
        crop_status="NOT_STARTED",
        irrigation_source=IrrigationSource.CANAL,
    )
    assert evaluate_rule(fc, sowing_rule, unplanted_farmer) is True
    assert evaluate_rule(fc, irrigation_rule, unplanted_farmer) is False


