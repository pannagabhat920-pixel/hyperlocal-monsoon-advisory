"""
Shared test configuration.

Uses NullPool for the test database engine to avoid asyncpg connection
reuse across different asyncio event loops (which causes "Future attached
to a different loop" errors when each test runs with its own loop).
"""
import asyncio
import os
import redis

# Set all env vars BEFORE any app imports so Pydantic settings picks them up
os.environ["DATABASE_URL"] = "postgresql+asyncpg://pannaga:pannaga@postgis:5432/pannaga"
os.environ["REDIS_URL"] = "redis://redis:6379/0"
os.environ["SECRET_KEY"] = "supersecretkey_for_development_only_please_change_in_production_minimum_32_characters"
os.environ["ENV"] = "test"
os.environ["MESSAGING_PROVIDER"] = "mock"
os.environ["DEV_OTP_ENABLED"] = "true"

import pytest
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

DATABASE_URL = os.environ["DATABASE_URL"]
REDIS_URL = os.environ["REDIS_URL"]


def make_test_engine():
    """NullPool engine: every connection is fresh, no cross-loop sharing."""
    return create_async_engine(DATABASE_URL, echo=False, poolclass=NullPool)


def clear_otp_rate_limit(phone: str) -> None:
    """Synchronously delete Redis OTP rate-limit key for a phone number."""
    try:
        r = redis.from_url(REDIS_URL)
        r.delete(f"otp_rate:{phone}")
        r.close()
    except Exception:
        pass


# Shared counter for unique phone numbers across all tests
_phone_counter = iter(range(930_000_0001, 930_000_9999))


def next_phone() -> str:
    """Return a fresh unique phone number for each test."""
    return f"+91{next(_phone_counter)}"
