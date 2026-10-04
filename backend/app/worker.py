"""
Celery tasks for Phase 3 data & ML pipeline.

Beat schedule:
  - Every hour  : refresh BlockForecastAgg materialized view
  - Every day   : ingest NOAA/BoM climate indices → global_indices
  - Every week  : refresh Open-Meteo forecasts → grid_forecasts (SIMULATED)
  - Every week  : re-run advisory generation
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone

from celery import Celery

from app.core.config import settings

logger = logging.getLogger(__name__)

celery_app = Celery(
    "pannaga",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    beat_schedule={
        "refresh-matview-hourly": {
            "task": "app.worker.refresh_materialized_view",
            "schedule": 3600,
        },
        "ingest-indices-daily": {
            "task": "app.worker.ingest_climate_indices",
            "schedule": 86400,
        },
        "refresh-forecasts-weekly": {
            "task": "app.worker.refresh_forecasts",
            "schedule": 7 * 86400,
        },
        "generate-advisories-weekly": {
            "task": "app.worker.generate_advisories",
            "schedule": 7 * 86400,
        },
    },
)


def _run_async(coro):
    """Run an async coroutine inside a Celery (sync) task."""
    return asyncio.run(coro)


# ─── Materialized View Refresh ────────────────────────────────────────────────

@celery_app.task(name="app.worker.refresh_materialized_view", bind=True, max_retries=3)
def refresh_materialized_view(self):
    """Refresh BlockForecastAgg materialized view (CONCURRENTLY)."""
    async def _inner():
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy import text

        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        async with engine.begin() as conn:
            await conn.execute(text(
                "REFRESH MATERIALIZED VIEW CONCURRENTLY block_forecast_agg"
            ))
        await engine.dispose()
        logger.info("[Worker] BlockForecastAgg refreshed")

    try:
        _run_async(_inner())
    except Exception as exc:
        logger.error(f"[Worker] refresh_materialized_view failed: {exc}")
        raise self.retry(exc=exc, countdown=60)


# ─── Climate Index Ingest ─────────────────────────────────────────────────────

@celery_app.task(name="app.worker.ingest_climate_indices", bind=True, max_retries=3)
def ingest_climate_indices(self):
    """
    Fetch NOAA ONI, MJO, and DMI. Upsert into global_indices table.
    Marks data_source as LIVE if all three fetches succeed, else HINDCAST.
    """
    async def _inner():
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker

        from app.ingest.indices import fetch_all_indices
        from app.models.climate import GlobalIndices
        from app.models.enums import DataSource

        indices = fetch_all_indices()
        source = DataSource.LIVE if indices["all_live"] else DataSource.HINDCAST

        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with Session() as db:
            record = GlobalIndices(
                issue_date=date.today(),
                nino34=indices["nino34"],
                iod_dmi=indices["iod_dmi"],
                mjo_phase=indices["mjo_phase"],
                mjo_amplitude=indices["mjo_amplitude"],
                data_source=source,
                source_url_oni=None,
                source_url_mjo=None,
                source_url_dmi=None,
            )
            db.add(record)
            await db.commit()
        await engine.dispose()
        logger.info(f"[Worker] Indices ingested: source={source.value}")
        return {"source": source.value, "nino34": indices["nino34"]}

    try:
        return _run_async(_inner())
    except Exception as exc:
        logger.error(f"[Worker] ingest_climate_indices failed: {exc}")
        raise self.retry(exc=exc, countdown=300)


# ─── Forecast Generation ──────────────────────────────────────────────────────

@celery_app.task(name="app.worker.refresh_forecasts", bind=True, max_retries=2)
def refresh_forecasts(self):
    """
    For all Panchayats in DB:
      1. Fetch latest GlobalIndices
      2. Try to get Open-Meteo NWP data (LIVE if succeeds)
      3. Run simulator → SIMULATED forecasts for lead weeks 1-4
      4. Upsert GridForecast rows
      5. Refresh materialized view
    """
    async def _inner():
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy import select, text

        from app.ingest.forecast import fetch_open_meteo
        from app.ml.simulator import simulate_forecast
        from app.models.climate import GlobalIndices, GridForecast, ModelVersion
        from app.models.geography import Panchayat
        from app.models.enums import DataSource

        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with Session() as db:
            # Get latest indices
            idx_result = await db.execute(
                select(GlobalIndices).order_by(GlobalIndices.created_at.desc()).limit(1)
            )
            idx = idx_result.scalar_one_or_none()
            nino34 = idx.nino34 if idx else 0.0
            iod_dmi = idx.iod_dmi if idx else 0.0
            mjo_phase = idx.mjo_phase if idx else 3
            mjo_amplitude = idx.mjo_amplitude if idx else 1.0

            # Get or create untrained ModelVersion
            mv_result = await db.execute(
                select(ModelVersion).where(ModelVersion.is_active == True).limit(1)
            )
            model_version = mv_result.scalar_one_or_none()
            model_version_id = model_version.id if model_version else None

            # Get all Panchayats
            pan_result = await db.execute(select(Panchayat))
            panchayats = pan_result.scalars().all()

            issue_date = date.today()
            total = 0

            for pan in panchayats:
                # Get panchayat centroid (lon, lat from WKB point if available)
                lat = 19.0 + pan.id * 0.05  # fallback: spread across India
                lon = 74.0 + pan.id * 0.03

                # Try to get Open-Meteo NWP
                nwp_data = None
                if settings.FEATURE_FLAGS.get("enable_open_meteo", True):
                    nwp_data = fetch_open_meteo(lat, lon)

                for lead_week in (1, 2, 3, 4):
                    fc = simulate_forecast(
                        panchayat_id=pan.id,
                        lat=lat,
                        lon=lon,
                        lead_week=lead_week,
                        nino34=nino34,
                        iod_dmi=iod_dmi,
                        mjo_phase=mjo_phase,
                        mjo_amplitude=mjo_amplitude,
                        issue_date=issue_date,
                        open_meteo_weekly=nwp_data,
                    )
                    gf = GridForecast(
                        panchayat_id=pan.id,
                        model_version_id=model_version_id,
                        issue_date=fc["issue_date"],
                        target_week_start=fc["target_week_start"],
                        target_week_end=fc["target_week_end"],
                        lead_week=fc["lead_week"],
                        onset_prob=fc["onset_prob"],
                        break_prob=fc["break_prob"],
                        excess_rain_prob=fc["excess_rain_prob"],
                        p10_rainfall_mm=fc["p10_rainfall_mm"],
                        p50_rainfall_mm=fc["p50_rainfall_mm"],
                        p90_rainfall_mm=fc["p90_rainfall_mm"],
                        confidence=fc["confidence"],
                        data_source=DataSource.SIMULATED,
                        features_json=fc["features_json"],
                        shap_values_json=None,
                    )
                    db.add(gf)
                    total += 1

            await db.commit()

            # Refresh materialized view
            async with engine.begin() as conn:
                await conn.execute(text(
                    "REFRESH MATERIALIZED VIEW CONCURRENTLY block_forecast_agg"
                ))

        await engine.dispose()
        logger.info(f"[Worker] Forecasts generated: {total} rows")
        return {"total": total}

    try:
        return _run_async(_inner())
    except Exception as exc:
        logger.error(f"[Worker] refresh_forecasts failed: {exc}")
        raise self.retry(exc=exc, countdown=600)


@celery_app.task(name="app.worker.generate_advisories", bind=True, max_retries=2)
def generate_advisories(self):
    """Run full advisory generation cycle across latest forecasts."""
    async def _inner():
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker
        from app.services.agronomy_engine import run_full_advisory_cycle
        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with Session() as db:
            result = await run_full_advisory_cycle(db)
        await engine.dispose()
        return result
    try:
        return _run_async(_inner())
    except Exception as exc:
        logger.error(f"[Worker] generate_advisories failed: {exc}")
        raise self.retry(exc=exc, countdown=300)


@celery_app.task(
    name="app.worker.dispatch_notification_task",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    retry_backoff=True,
    retry_backoff_max=600,
)
def dispatch_notification_task(self, advisory_id: int, recipient_id: int, channel_str: str = "SMS"):
    """
    Celery worker task for idempotent notification dispatch with exponential backoff.
    """
    async def _inner():
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy import select
        from app.models.agronomy import GeneratedAdvisory
        from app.models.users import User
        from app.models.enums import NotificationChannel
        from app.services.messaging_gateway import dispatch_notification

        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with Session() as db:
            adv_res = await db.execute(select(GeneratedAdvisory).where(GeneratedAdvisory.id == advisory_id))
            adv = adv_res.scalar_one_or_none()
            user_res = await db.execute(select(User).where(User.id == recipient_id))
            user = user_res.scalar_one_or_none()
            if not adv or not user:
                logger.error(f"[Worker] Cannot dispatch: adv {advisory_id} or user {recipient_id} not found")
                return {"status": "not_found"}

            log = await dispatch_notification(
                advisory=adv,
                recipient_phone=user.phone_number,
                recipient_id=user.id,
                message_body=f"{adv.headline}\n\n{adv.content}",
                channel=NotificationChannel(channel_str.upper()),
                db=db,
            )
            return {"status": log.dispatch_status.value, "log_id": log.id}
    try:
        return _run_async(_inner())
    except Exception as exc:
        logger.error(f"[Worker] Notification dispatch failed: {exc}")
        raise self.retry(exc=exc)

