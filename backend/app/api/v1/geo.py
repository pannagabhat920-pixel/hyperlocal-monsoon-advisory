"""
Geo API Router.

Provides:
  - Vector Tiles (MVT) for blocks (low zoom) and panchayats (high zoom) via PostGIS ST_AsMVT
  - GeoJSON endpoints for 2D Choropleth fallback rendering
  - Search (Panchayat / Block / District)
  - Point-in-polygon reverse lookup
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/geo", tags=["Geography & Maps"])


# ─── 1. Vector Tiles (MVT) ───────────────────────────────────────────────────

@router.get("/tiles/blocks/{z}/{x}/{y}.pbf", summary="MVT tiles for blocks (low zoom)")
async def get_block_mvt_tile(
    z: int, x: int, y: int,
    lead_week: int = Query(1, ge=1, le=4),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate Mapbox Vector Tile (MVT) for blocks at tile coordinate (z, x, y).
    Joins block_forecast_agg for fast rendering at low zoom levels (zoom 4 - 10).
    """
    tile_sql = text("""
        WITH bounds AS (
            SELECT ST_TileEnvelope(:z, :x, :y) AS geom
        ),
        mvt_geom AS (
            SELECT
                b.id,
                b.name,
                b.district_id,
                COALESCE(fa.avg_onset_prob, 0.40) AS onset_prob,
                COALESCE(fa.avg_break_prob, 0.25) AS break_prob,
                COALESCE(fa.avg_excess_rain_prob, 0.20) AS excess_rain_prob,
                COALESCE(fa.avg_p50_rainfall_mm, 35.0) AS p50_rainfall_mm,
                ST_AsMVTGeom(ST_Transform(b.geom, 3857), bounds.geom, 4096, 64, true) AS geom
            FROM blocks b
            CROSS JOIN bounds
            LEFT JOIN block_forecast_agg fa ON b.id = fa.block_id AND fa.lead_week = :lead_week
            WHERE b.geom && ST_Transform(bounds.geom, 4326)
        )
        SELECT ST_AsMVT(mvt_geom.*, 'blocks', 4096, 'geom') AS mvt
        FROM mvt_geom;
    """)

    result = await db.execute(tile_sql, {"z": z, "x": x, "y": y, "lead_week": lead_week})
    tile_data = result.scalar() or b""

    return Response(
        content=bytes(tile_data),
        media_type="application/vnd.mapbox-vector-tile",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/tiles/panchayats/{z}/{x}/{y}.pbf", summary="MVT tiles for panchayats (high zoom)")
async def get_panchayat_mvt_tile(
    z: int, x: int, y: int,
    lead_week: int = Query(1, ge=1, le=4),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate Mapbox Vector Tile (MVT) for Gram Panchayats at tile coordinate (z, x, y).
    Provides hyperlocal probability attributes for 3D extrusion at zoom 10 - 18.
    """
    tile_sql = text("""
        WITH bounds AS (
            SELECT ST_TileEnvelope(:z, :x, :y) AS geom
        ),
        latest_fc AS (
            SELECT DISTINCT ON (panchayat_id)
                panchayat_id,
                onset_prob,
                break_prob,
                excess_rain_prob,
                p50_rainfall_mm,
                confidence,
                data_source
            FROM grid_forecasts
            WHERE lead_week = :lead_week
            ORDER BY panchayat_id, issue_date DESC
        ),
        mvt_geom AS (
            SELECT
                p.id,
                p.name,
                p.block_id,
                COALESCE(fc.onset_prob, 0.45) AS onset_prob,
                COALESCE(fc.break_prob, 0.20) AS break_prob,
                COALESCE(fc.excess_rain_prob, 0.25) AS excess_rain_prob,
                COALESCE(fc.p50_rainfall_mm, 40.0) AS p50_rainfall_mm,
                COALESCE(fc.confidence, 0.65) AS confidence,
                COALESCE(fc.data_source::text, 'SIMULATED') AS data_source,
                ST_AsMVTGeom(ST_Transform(p.geom, 3857), bounds.geom, 4096, 64, true) AS geom
            FROM panchayats p
            CROSS JOIN bounds
            LEFT JOIN latest_fc fc ON p.id = fc.panchayat_id
            WHERE p.geom && ST_Transform(bounds.geom, 4326)
        )
        SELECT ST_AsMVT(mvt_geom.*, 'panchayats', 4096, 'geom') AS mvt
        FROM mvt_geom;
    """)

    result = await db.execute(tile_sql, {"z": z, "x": x, "y": y, "lead_week": lead_week})
    tile_data = result.scalar() or b""

    return Response(
        content=bytes(tile_data),
        media_type="application/vnd.mapbox-vector-tile",
        headers={"Cache-Control": "public, max-age=3600"},
    )


# ─── 2. GeoJSON Endpoints (for 2D Choropleth Fallback) ────────────────────────

@router.get("/geojson/panchayats", summary="GeoJSON FeatureCollection for panchayats (2D Fallback)")
async def get_panchayats_geojson(
    lead_week: int = Query(1, ge=1, le=4),
    block_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Returns GeoJSON FeatureCollection of panchayats with forecast properties.
    Used by ChoroplethMap2D fallback when WebGL is unavailable.
    """
    filter_sql = "WHERE p.block_id = :block_id" if block_id else ""
    sql = text(f"""
        WITH latest_fc AS (
            SELECT DISTINCT ON (panchayat_id)
                panchayat_id,
                onset_prob,
                break_prob,
                excess_rain_prob,
                p10_rainfall_mm,
                p50_rainfall_mm,
                p90_rainfall_mm,
                confidence,
                data_source
            FROM grid_forecasts
            WHERE lead_week = :lead_week
            ORDER BY panchayat_id, issue_date DESC
        )
        SELECT jsonb_build_object(
            'type', 'FeatureCollection',
            'features', COALESCE(jsonb_agg(
                jsonb_build_object(
                    'type', 'Feature',
                    'id', p.id,
                    'geometry', ST_AsGeoJSON(p.geom)::jsonb,
                    'properties', jsonb_build_object(
                        'id', p.id,
                        'name', p.name,
                        'block_id', p.block_id,
                        'block_name', b.name,
                        'district_name', d.name,
                        'state_name', s.name,
                        'onset_prob', COALESCE(fc.onset_prob, 0.45),
                        'break_prob', COALESCE(fc.break_prob, 0.20),
                        'excess_rain_prob', COALESCE(fc.excess_rain_prob, 0.25),
                        'p10_rainfall_mm', COALESCE(fc.p10_rainfall_mm, 20.0),
                        'p50_rainfall_mm', COALESCE(fc.p50_rainfall_mm, 40.0),
                        'p90_rainfall_mm', COALESCE(fc.p90_rainfall_mm, 65.0),
                        'confidence', COALESCE(fc.confidence, 0.65),
                        'data_source', COALESCE(fc.data_source::text, 'SIMULATED'),
                        'centroid_lon', ST_X(p.centroid),
                        'centroid_lat', ST_Y(p.centroid)
                    )
                )
            ), '[]'::jsonb)
        )
        FROM panchayats p
        JOIN blocks b ON p.block_id = b.id
        JOIN districts d ON b.district_id = d.id
        JOIN states s ON d.state_id = s.id
        LEFT JOIN latest_fc fc ON p.id = fc.panchayat_id
        {filter_sql};
    """)
    params = {"lead_week": lead_week}
    if block_id:
        params["block_id"] = block_id

    result = await db.execute(sql, params)
    geojson = result.scalar()
    return geojson or {"type": "FeatureCollection", "features": []}


# ─── 3. Search & Point-in-Polygon Lookup ──────────────────────────────────────

@router.get("/search", summary="Search geography by query string")
async def search_geo(
    q: str = Query(..., min_length=2),
    db: AsyncSession = Depends(get_db),
):
    """
    Search panchayats, blocks, and districts. Returns coordinates and hierarchy.
    """
    pattern = f"%{q.strip().lower()}%"
    sql = text("""
        SELECT
            p.id AS panchayat_id,
            p.name AS panchayat_name,
            b.id AS block_id,
            b.name AS block_name,
            d.name AS district_name,
            s.name AS state_name,
            ST_X(p.centroid) AS lon,
            ST_Y(p.centroid) AS lat
        FROM panchayats p
        JOIN blocks b ON p.block_id = b.id
        JOIN districts d ON b.district_id = d.id
        JOIN states s ON d.state_id = s.id
        WHERE LOWER(p.name) LIKE :pat OR LOWER(b.name) LIKE :pat OR LOWER(d.name) LIKE :pat
        ORDER BY p.name ASC
        LIMIT 10;
    """)
    result = await db.execute(sql, {"pat": pattern})
    rows = result.mappings().all()

    return {
        "query": q,
        "results": [dict(r) for r in rows],
    }


@router.get("/lookup", summary="Point-in-polygon lookup from lat/lon")
async def point_in_polygon_lookup(
    lat: float = Query(..., ge=6.0, le=38.0),
    lon: float = Query(..., ge=68.0, le=98.0),
    db: AsyncSession = Depends(get_db),
):
    """Finds which panchayat, block, and district contains (lat, lon)."""
    sql = text("""
        SELECT
            p.id AS panchayat_id,
            p.name AS panchayat_name,
            b.id AS block_id,
            b.name AS block_name,
            d.name AS district_name,
            s.name AS state_name
        FROM panchayats p
        JOIN blocks b ON p.block_id = b.id
        JOIN districts d ON b.district_id = d.id
        JOIN states s ON d.state_id = s.id
        WHERE ST_Contains(p.geom, ST_SetSRID(ST_Point(:lon, :lat), 4326))
        LIMIT 1;
    """)
    result = await db.execute(sql, {"lat": lat, "lon": lon})
    row = result.mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="No Gram Panchayat found for coordinate.")
    return dict(row)
