"""
Webhook endpoints.

POST /api/v1/webhooks/twilio/status - Twilio delivery status callback.

Security: validates X-Twilio-Signature using HMAC-SHA1 before processing.
Invalid signatures return 403 immediately.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
from base64 import b64encode
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.agronomy import NotificationLog
from app.models.enums import NotificationStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")


def validate_twilio_signature(
    auth_token: str,
    url: str,
    params: dict,
    signature: str,
) -> bool:
    """
    Validate Twilio webhook signature (HMAC-SHA1).

    Algorithm: https://www.twilio.com/docs/usage/webhooks/webhooks-security
      1. Concatenate URL + sorted params (key+value)
      2. HMAC-SHA1 with auth_token as key
      3. Base64-encode and compare (constant-time)
    """
    if not auth_token:
        logger.warning("[Webhook] TWILIO_AUTH_TOKEN not set — rejecting all webhooks")
        return False

    # Build the string to sign
    sorted_params = sorted(params.items())
    s = url + "".join(k + v for k, v in sorted_params)

    expected = b64encode(
        hmac.new(auth_token.encode("utf-8"), s.encode("utf-8"), hashlib.sha1).digest()
    ).decode()

    return hmac.compare_digest(expected, signature)


@router.post(
    "/twilio/status",
    summary="Twilio delivery status callback",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def twilio_status_callback(
    request: Request,
    x_twilio_signature: Optional[str] = Header(None, alias="X-Twilio-Signature"),
    MessageSid: Optional[str] = Form(None),
    MessageStatus: Optional[str] = Form(None),
    To: Optional[str] = Form(None),
    From_: Optional[str] = Form(None, alias="From"),
    db: AsyncSession = Depends(get_db),
):
    """
    Update NotificationLog.dispatch_status from Twilio's delivery callback.

    Status mapping:
      sent      → SENT
      delivered → DELIVERED
      failed / undelivered → FAILED
    """
    # ── Signature validation ──────────────────────────────────────────────────
    if not x_twilio_signature:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing X-Twilio-Signature header",
        )

    from app.core.config import settings
    public_base = (getattr(settings, "PUBLIC_BASE_URL", "") or os.getenv("PUBLIC_BASE_URL", "")).rstrip("/")
    if public_base:
        url_path = request.url.path
        if request.url.query:
            url_path = f"{url_path}?{request.url.query}"
        public_url = f"{public_base}{url_path}"
    else:
        public_url = str(request.url)

    form_data = dict(await request.form())
    form_str = {k: str(v) for k, v in form_data.items()}

    # Verify against exact public URL (and request.url as local fallback) using constant-time compare
    is_valid = validate_twilio_signature(TWILIO_AUTH_TOKEN, public_url, form_str, x_twilio_signature)
    if not is_valid and public_url != str(request.url):
        is_valid = validate_twilio_signature(TWILIO_AUTH_TOKEN, str(request.url), form_str, x_twilio_signature)

    if not is_valid:
        logger.warning(f"[Webhook] Invalid Twilio signature from {request.client.host if request.client else 'unknown'}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid Twilio signature",
        )


    if not MessageSid or not MessageStatus:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing fields")

    # ── Update NotificationLog ────────────────────────────────────────────────
    status_map = {
        "sent":          NotificationStatus.SENT,
        "delivered":     NotificationStatus.DELIVERED,
        "failed":        NotificationStatus.FAILED,
        "undelivered":   NotificationStatus.FAILED,
        "queued":        None,  # Ignore intermediate state
        "sending":       None,
    }

    new_status = status_map.get(MessageStatus.lower())
    if new_status is None:
        logger.debug(f"[Webhook] Ignoring intermediate status: {MessageStatus}")
        return  # 204 No Content

    result = await db.execute(
        select(NotificationLog).where(
            NotificationLog.provider_message_id == MessageSid
        )
    )
    log = result.scalar_one_or_none()

    if log:
        log.dispatch_status = new_status
        if new_status == NotificationStatus.DELIVERED:
            from datetime import datetime, timezone
            log.delivered_at = datetime.now(timezone.utc)
        await db.commit()
        logger.info(f"[Webhook] Updated {MessageSid} → {new_status.value}")
    else:
        logger.warning(f"[Webhook] No NotificationLog found for SID={MessageSid}")
