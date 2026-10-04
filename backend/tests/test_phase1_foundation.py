import pytest
import asyncio
import os
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://pannaga:pannaga@postgis:5432/pannaga",
)

async def run_query(sql: str):
    """Helper: open a fresh engine+session, run sql, return rows, dispose."""
    engine = create_async_engine(DATABASE_URL, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as session:
        result = await session.execute(text(sql))
        rows = result.fetchall()
    await engine.dispose()
    return rows


# ─── Liveness / Readiness ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_healthz():
    """GET /healthz must return 200 {"status": "ok"}."""
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_readyz_returns_ready():
    """GET /readyz must show database and redis healthy."""
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/readyz")
    data = resp.json()
    assert resp.status_code == 200
    assert data["database"] == "healthy"
    assert data["redis"] == "healthy"


# ─── PostGIS ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_postgis_extension():
    """PostGIS extension must be enabled."""
    rows = await run_query("SELECT PostGIS_Version()")
    assert rows and rows[0][0] is not None


# ─── Tables ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_all_tables_exist():
    """All 16 core tables must exist after migrations."""
    expected = {
        "states", "districts", "blocks", "panchayats",
        "users", "farmer_profiles", "officer_jurisdictions",
        "otp_verifications", "refresh_tokens", "audit_logs",
        "global_indices", "model_versions", "grid_forecasts",
        "agronomic_rules", "generated_advisories", "notification_logs",
    }
    rows = await run_query("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    existing = {r[0] for r in rows}
    for table in expected:
        assert table in existing, f"Missing table: {table}"


# ─── Materialized View ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_materialized_view_exists():
    """block_forecast_agg materialized view must exist."""
    rows = await run_query(
        "SELECT matviewname FROM pg_matviews WHERE schemaname='public' AND matviewname='block_forecast_agg'"
    )
    assert rows, "block_forecast_agg materialized view not found"


@pytest.mark.asyncio
async def test_materialized_view_queryable():
    """block_forecast_agg must be SELECTable (populated by seed)."""
    rows = await run_query("SELECT COUNT(*) FROM block_forecast_agg")
    count = rows[0][0]
    assert count > 0, "block_forecast_agg should contain rows after seeding"


# ─── Enum Types ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_enum_types_exist():
    """All 7 custom enum types must be in pg_type."""
    rows = await run_query(
        "SELECT typname FROM pg_type WHERE typtype='e' AND typnamespace='public'::regnamespace"
    )
    existing = {r[0] for r in rows}
    required = {
        "userrole", "irrigationsource", "datasource",
        "advisoryseverity", "advisoryapprovalstatus",
        "notificationchannel", "notificationstatus",
    }
    for e in required:
        assert e in existing, f"Missing enum type: {e}"


@pytest.mark.asyncio
async def test_blocked_simulated_enum_value():
    """BLOCKED_SIMULATED must be a valid notificationstatus enum value."""
    rows = await run_query(
        "SELECT enumlabel FROM pg_enum "
        "JOIN pg_type ON pg_enum.enumtypid=pg_type.oid "
        "WHERE pg_type.typname='notificationstatus'"
    )
    values = {r[0] for r in rows}
    assert "BLOCKED_SIMULATED" in values, "BLOCKED_SIMULATED missing from notificationstatus"


@pytest.mark.asyncio
async def test_data_source_enum_has_all_values():
    """datasource enum must include LIVE, HINDCAST, SIMULATED."""
    rows = await run_query(
        "SELECT enumlabel FROM pg_enum "
        "JOIN pg_type ON pg_enum.enumtypid=pg_type.oid "
        "WHERE pg_type.typname='datasource'"
    )
    values = {r[0] for r in rows}
    assert {"LIVE", "HINDCAST", "SIMULATED"}.issubset(values)


# ─── Spatial Indexes ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gist_indexes_exist():
    """At least 4 GIST spatial indexes must exist on geometry columns."""
    rows = await run_query(
        "SELECT indexname FROM pg_indexes "
        "WHERE schemaname='public' AND indexdef ILIKE '%gist%'"
    )
    assert len(rows) >= 4, f"Expected >=4 GIST indexes, got {len(rows)}: {[r[0] for r in rows]}"


# ─── Seed Data Integrity ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_seed_panchayat_count():
    """Seed must have loaded at least 15 Gram Panchayats."""
    rows = await run_query("SELECT COUNT(*) FROM panchayats WHERE is_synthetic_boundary=true")
    assert rows[0][0] >= 15, f"Expected >=15 panchayats, got {rows[0][0]}"


@pytest.mark.asyncio
async def test_seed_forecasts_all_have_simulated_source():
    """All seeded forecasts must have data_source=SIMULATED (data honesty)."""
    rows = await run_query(
        "SELECT COUNT(*) FROM grid_forecasts WHERE data_source != 'SIMULATED'"
    )
    assert rows[0][0] == 0, "Found non-SIMULATED forecasts in seeded data — data honesty violation"


@pytest.mark.asyncio
async def test_seed_blocked_simulated_notification():
    """At least one NotificationLog with BLOCKED_SIMULATED must exist (data honesty guard)."""
    rows = await run_query(
        "SELECT COUNT(*) FROM notification_logs WHERE dispatch_status='BLOCKED_SIMULATED'"
    )
    assert rows[0][0] >= 1, "No BLOCKED_SIMULATED notification log found"
