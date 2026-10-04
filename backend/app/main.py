from fastapi import FastAPI, Depends, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis
from typing import Dict, Any

from app.core.config import settings
from app.core.errors import (
    AppException,
    app_exception_handler,
    http_exception_handler,
    validation_exception_handler,
    generic_exception_handler,
)
from app.db.session import get_db
from app.api.v1 import auth, me, advisories, officer, webhooks

from app.core.config import settings, validate_production_settings

# Fail-fast validation in production
validate_production_settings()

app = FastAPI(
    title="Pannaga API",
    version="0.1.0",
    description="Hyperlocal Monsoon Onset & Break Prediction System for India",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS Middleware
origins = settings.CORS_ORIGINS if isinstance(settings.CORS_ORIGINS, list) else [settings.CORS_ORIGINS]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception Handlers (RFC 7807)
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

from app.api.v1 import auth, me, advisories, officer, webhooks, geo, forecasts

# Routers
app.include_router(auth.router)                  # Has /api/v1/auth internally
app.include_router(me.router)                    # Has /api/v1/me internally
app.include_router(advisories.router, prefix="/api/v1")  # /advisories -> /api/v1/advisories
app.include_router(officer.router,    prefix="/api/v1")  # /officer    -> /api/v1/officer
app.include_router(webhooks.router,   prefix="/api/v1")  # /webhooks   -> /api/v1/webhooks
app.include_router(geo.router,        prefix="/api/v1")  # /geo        -> /api/v1/geo
app.include_router(forecasts.router,  prefix="/api/v1")  # /forecasts  -> /api/v1/forecasts

from pathlib import Path
from fastapi.staticfiles import StaticFiles
_media_dir = Path("/app/media")
_media_dir.mkdir(parents=True, exist_ok=True)
(_media_dir / "audio").mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=str(_media_dir)), name="media")






@app.get("/healthz", summary="Liveness probe", tags=["Health"])
async def healthz():
    return {"status": "ok"}


@app.get("/readyz", summary="Readiness probe", tags=["Health"])
async def readyz(db: AsyncSession = Depends(get_db)):
    readiness: Dict[str, Any] = {
        "status": "ready",
        "database": "unknown",
        "redis": "unknown",
        "last_ingest": None,
    }
    healthy = True

    try:
        db_check = await db.execute(text("SELECT 1"))
        if db_check.scalar() == 1:
            readiness["database"] = "healthy"
        else:
            readiness["database"] = "unhealthy"
            healthy = False
    except Exception as e:
        readiness["database"] = f"unhealthy: {str(e)}"
        healthy = False

    try:
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        pong = await r.ping()
        await r.aclose()
        if pong:
            readiness["redis"] = "healthy"
        else:
            readiness["redis"] = "unhealthy"
            healthy = False
    except Exception as e:
        readiness["redis"] = f"unhealthy: {str(e)}"
        healthy = False

    try:
        ingest_res = await db.execute(text("SELECT MAX(created_at) FROM global_indices"))
        last_ingest_val = ingest_res.scalar()
        readiness["last_ingest"] = str(last_ingest_val) if last_ingest_val else "none_recorded"
    except Exception:
        readiness["last_ingest"] = "tables_not_initialized"

    if not healthy:
        readiness["status"] = "unhealthy"
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=readiness)

    return readiness
