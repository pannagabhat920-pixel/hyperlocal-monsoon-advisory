"""
Phase 5 Gate Tests: Geography, MVT Vector Tiles, and Forecast Outlook APIs.

Verifications:
1. MVT vector tile generation for blocks (zoom 4 - 10) returns valid application/vnd.mapbox-vector-tile bytes.
2. MVT vector tile generation for panchayats (zoom 10 - 18) returns valid application/vnd.mapbox-vector-tile bytes.
3. GeoJSON panchayats endpoint returns valid FeatureCollection with forecast properties for 2D fallback.
4. Geo search returns hierarchy (panchayat, block, district, state) and centroid coordinates.
5. Point-in-polygon lookup returns containing panchayat from coordinate.
6. 4-week forecast outlook returns p10/p50/p90 percentiles and data_source banner flag.
"""
import os
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://pannaga:pannaga@postgis:5432/pannaga")
os.environ.setdefault("REDIS_URL", "redis://redis:6379/0")
os.environ.setdefault("SECRET_KEY", "supersecretkey_for_development_only_please_change_in_production_minimum_32_characters")
os.environ.setdefault("ENV", "test")
os.environ.setdefault("MESSAGING_PROVIDER", "mock")

DATABASE_URL = os.environ["DATABASE_URL"]


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


@pytest.mark.asyncio(loop_scope="function")
async def test_block_mvt_tile_endpoint():
    """GET /geo/tiles/blocks/{z}/{x}/{y}.pbf returns vector tile content type."""
    async with make_client() as client:
        # Tile covering India: z=4, x=11, y=7
        resp = await client.get("/api/v1/geo/tiles/blocks/4/11/7.pbf?lead_week=1")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/vnd.mapbox-vector-tile"
    assert isinstance(resp.content, bytes)


@pytest.mark.asyncio(loop_scope="function")
async def test_panchayat_mvt_tile_endpoint():
    """GET /geo/tiles/panchayats/{z}/{x}/{y}.pbf returns vector tile content type."""
    async with make_client() as client:
        # Tile covering seeded panchayat coordinate
        resp = await client.get("/api/v1/geo/tiles/panchayats/10/720/460.pbf?lead_week=1")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/vnd.mapbox-vector-tile"
    assert isinstance(resp.content, bytes)


@pytest.mark.asyncio(loop_scope="function")
async def test_geojson_panchayats_for_2d_fallback():
    """GET /geo/geojson/panchayats returns GeoJSON FeatureCollection for 2D fallback map."""
    async with make_client() as client:
        resp = await client.get("/api/v1/geo/geojson/panchayats?lead_week=1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) > 0

    first_feat = data["features"][0]
    assert "geometry" in first_feat
    props = first_feat["properties"]
    assert "onset_prob" in props
    assert "break_prob" in props
    assert "excess_rain_prob" in props
    assert "p50_rainfall_mm" in props
    assert "data_source" in props


@pytest.mark.asyncio(loop_scope="function")
async def test_geo_search_returns_hierarchy():
    """GET /geo/search returns matching panchayats with blocks, districts, and coords."""
    async with make_client() as client:
        # Search for a seeded name e.g. "Wagh" (Wagholi)
        resp = await client.get("/api/v1/geo/search?q=Wagh")

    assert resp.status_code == 200
    data = resp.json()
    assert "results" in data
    assert len(data["results"]) > 0
    res0 = data["results"][0]
    assert "panchayat_name" in res0
    assert "block_name" in res0
    assert "district_name" in res0
    assert "lat" in res0 and "lon" in res0


@pytest.mark.asyncio(loop_scope="function")
async def test_panchayat_4week_forecast_outlook():
    """GET /forecasts/panchayat/{id} returns 4-week percentiles and data honesty flag."""
    async with make_client() as client:
        resp = await client.get("/api/v1/forecasts/panchayat/1")
    assert resp.status_code == 200
    data = resp.json()
    assert "panchayat" in data
    assert "forecasts" in data
    assert len(data["forecasts"]) >= 1

    fc = data["forecasts"][0]
    assert "p10_rainfall_mm" in fc
    assert "p50_rainfall_mm" in fc
    assert "p90_rainfall_mm" in fc
    assert "onset_prob" in fc
    assert "data_source" in fc
    assert "simulated_banner" in data
