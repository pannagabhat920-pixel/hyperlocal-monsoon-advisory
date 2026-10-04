"""
Messaging Gateway — provider interface for WhatsApp, SMS dispatch.

Providers (selected by MESSAGING_PROVIDER env var):
  - "console"  : print to stdout (local dev)
  - "mock"     : return fake SIDs, write to NotificationLog (tests)
  - "twilio"   : real Twilio API (PRODUCTION ONLY)

Non-negotiables enforced here:
  1. data_source=SIMULATED → always BLOCKED_SIMULATED, never calls provider
  2. MESSAGING_PROVIDER != "twilio" outside production → no real messages
  3. Idempotency key check: never dispatch the same (advisory, recipient) twice
  4. attempt_count is incremented on retry; permanent failure after 3 attempts
"""
from __future__ import annotations

import hashlib
import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agronomy import GeneratedAdvisory, NotificationLog
from app.models.enums import (
    DataSource,
    NotificationChannel,
    NotificationStatus,
)

logger = logging.getLogger(__name__)

MESSAGING_PROVIDER = os.getenv("MESSAGING_PROVIDER", "console")
ENV               = os.getenv("ENV", "development")
MAX_ATTEMPTS      = 3


# ─── Provider interface ────────────────────────────────────────────────────────

class MessagingProvider(ABC):
    """Abstract provider: send a single message."""

    @abstractmethod
    def send(
        self,
        to: str,
        body: str,
        channel: NotificationChannel,
    ) -> dict:
        """
        Send the message. Returns dict with:
          {
            "provider_message_id": str,
            "status": "sent" | "failed",
            "error": str | None,
          }
        """
        ...


class ConsoleProvider(MessagingProvider):
    """Prints messages to stdout — dev only."""

    def send(self, to: str, body: str, channel: NotificationChannel) -> dict:
        print(f"\n[ConsoleProvider] → {channel.value} to {to}\n{body}\n")
        return {"provider_message_id": f"console_{id(body)}", "status": "sent", "error": None}


class MockProvider(MessagingProvider):
    """Returns fake SIDs — test only."""

    _counter = 0

    def send(self, to: str, body: str, channel: NotificationChannel) -> dict:
        MockProvider._counter += 1
        return {
            "provider_message_id": f"MOCK_SID_{MockProvider._counter:06d}",
            "status": "sent",
            "error": None,
        }


class TwilioProvider(MessagingProvider):
    """
    Real Twilio API. Only instantiatable in ENV=production.
    Guard is enforced here so a misconfigured deploy can't accidentally send.
    """

    def __init__(self):
        if ENV != "production":
            raise RuntimeError(
                f"TwilioProvider cannot be used in ENV={ENV!r}. "
                "Set ENV=production and provide TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN."
            )
        self.account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
        self.auth_token  = os.getenv("TWILIO_AUTH_TOKEN", "")
        self.from_number = os.getenv("TWILIO_FROM_NUMBER", "")
        self.wa_from     = os.getenv("TWILIO_WHATSAPP_FROM", "")
        if not all([self.account_sid, self.auth_token, self.from_number]):
            raise RuntimeError("TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER required")

    def send(self, to: str, body: str, channel: NotificationChannel) -> dict:
        try:
            from twilio.rest import Client  # type: ignore
            client = Client(self.account_sid, self.auth_token)
            if channel == NotificationChannel.WHATSAPP:
                msg = client.messages.create(
                    from_=f"whatsapp:{self.wa_from}",
                    to=f"whatsapp:{to}",
                    body=body,
                )
            else:
                msg = client.messages.create(from_=self.from_number, to=to, body=body)
            return {"provider_message_id": msg.sid, "status": "sent", "error": None}
        except Exception as e:
            return {"provider_message_id": None, "status": "failed", "error": str(e)}


def _get_provider() -> MessagingProvider:
    if MESSAGING_PROVIDER == "twilio":
        return TwilioProvider()
    elif MESSAGING_PROVIDER == "mock":
        return MockProvider()
    else:
        return ConsoleProvider()


# ─── Idempotency key ──────────────────────────────────────────────────────────

def make_idempotency_key(advisory_id: int, recipient_id: int, channel: str) -> str:
    """SHA-256 of (advisory_id, recipient_id, channel) → 16-char hex."""
    raw = f"{advisory_id}:{recipient_id}:{channel}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


# ─── Main dispatch function ───────────────────────────────────────────────────

async def dispatch_notification(
    advisory: GeneratedAdvisory,
    recipient_phone: str,
    recipient_id: int,
    message_body: str,
    channel: NotificationChannel,
    db: AsyncSession,
) -> NotificationLog:
    """
    Dispatch one notification.

    Safety checks (in order):
      1. SIMULATED data → write BLOCKED_SIMULATED, return immediately
      2. Idempotency: if already SENT/DELIVERED for this key, return existing log
      3. Call provider, update log
      4. If provider fails and attempt_count < MAX_ATTEMPTS, mark FAILED (retry later)
    """
    idem_key = make_idempotency_key(advisory.id, recipient_id, channel.value)

    # ── 1. Idempotency check on (recipient_user_id, advisory_id, channel) ─────
    existing_result = await db.execute(
        select(NotificationLog).where(
            NotificationLog.recipient_user_id == recipient_id,
            NotificationLog.advisory_id == advisory.id,
            NotificationLog.channel == channel,
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing and existing.dispatch_status in (
        NotificationStatus.SENT,
        NotificationStatus.DELIVERED,
        NotificationStatus.BLOCKED_SIMULATED,
        NotificationStatus.BLOCKED_NON_LIVE,
        NotificationStatus.BLOCKED_CONSENT,
        NotificationStatus.BLOCKED_OPT_OUT,
    ):
        logger.info(
            f"[Gateway] Idempotency hit: advisory={advisory.id} "
            f"recipient={recipient_id} channel={channel.value} status={existing.dispatch_status.value}"
        )
        return existing

    # ── 2. Consent & Channel Opt-Out Check (never raise; record blocked log) ───
    from app.models.users import User
    user_result = await db.execute(select(User).where(User.id == recipient_id))
    recipient_user = user_result.scalar_one_or_none()

    blocked_status = None
    if recipient_user:
        if recipient_user.opted_out_at is not None:
            blocked_status = NotificationStatus.BLOCKED_OPT_OUT
        elif not recipient_user.is_active or not recipient_user.consent_given_at:
            blocked_status = NotificationStatus.BLOCKED_CONSENT
        elif channel == NotificationChannel.WHATSAPP and not getattr(recipient_user, "whatsapp_consent", True):
            blocked_status = NotificationStatus.BLOCKED_CONSENT
        elif channel == NotificationChannel.SMS and not getattr(recipient_user, "sms_consent", True):
            blocked_status = NotificationStatus.BLOCKED_CONSENT

    if blocked_status:
        logger.info(f"[Gateway] Notification blocked for user {recipient_id}: {blocked_status.value}")
        if existing:
            existing.dispatch_status = blocked_status
            await db.commit()
            return existing
        log = NotificationLog(
            advisory_id=advisory.id,
            recipient_user_id=recipient_id,
            channel=channel,
            message_content=message_body,
            dispatch_status=blocked_status,
            provider_message_id=None,
            attempt_count=0,
            idempotency_key=idem_key,
        )
        db.add(log)
        await db.commit()
        return log

    # ── 3. Data Honesty: Block non-LIVE data (SIMULATED or HINDCAST) ────────────
    if advisory.data_source != DataSource.LIVE:
        source_blocked_status = (
            NotificationStatus.BLOCKED_SIMULATED
            if advisory.data_source == DataSource.SIMULATED
            else NotificationStatus.BLOCKED_NON_LIVE
        )
        if existing:
            return existing
        log = NotificationLog(
            advisory_id=advisory.id,
            recipient_user_id=recipient_id,
            channel=channel,
            message_content=message_body,
            dispatch_status=source_blocked_status,
            provider_message_id=None,
            attempt_count=0,
            idempotency_key=idem_key,
        )
        db.add(log)
        await db.commit()
        logger.info(
            f"[Gateway] Non-LIVE data blocked: advisory_id={advisory.id} "
            f"source={advisory.data_source.value} recipient={recipient_id}"
        )
        return log

    # ── 4. Retry check (update in-place on existing FAILED row) ────────────────
    log = existing
    if log and log.attempt_count >= MAX_ATTEMPTS:
        logger.warning(
            f"[Gateway] Max attempts ({MAX_ATTEMPTS}) reached for advisory={advisory.id}"
        )
        return log

    # ── 5. Provider Dispatch ──────────────────────────────────────────────────
    provider = _get_provider()
    result = provider.send(recipient_phone, message_body, channel)

    new_status = (
        NotificationStatus.SENT if result["status"] == "sent" else NotificationStatus.FAILED
    )

    if log:
        # In-place update for retrying FAILED rows (preserves unique index)
        log.dispatch_status = new_status
        log.provider_message_id = result.get("provider_message_id")
        log.attempt_count += 1
        if new_status == NotificationStatus.SENT:
            log.delivered_at = None
    else:
        log = NotificationLog(
            advisory_id=advisory.id,
            recipient_user_id=recipient_id,
            channel=channel,
            message_content=message_body,
            dispatch_status=new_status,
            provider_message_id=result.get("provider_message_id"),
            attempt_count=1,
            idempotency_key=idem_key,
        )
        db.add(log)

    await db.commit()
    logger.info(
        f"[Gateway] Dispatched: advisory={advisory.id} recipient={recipient_id} "
        f"channel={channel.value} status={new_status.value} "
        f"sid={result.get('provider_message_id')} attempt={log.attempt_count}"
    )
    return log

