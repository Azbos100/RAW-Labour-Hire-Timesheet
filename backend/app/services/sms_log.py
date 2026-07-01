"""Persist outbound SMS records for the admin Alerts audit trail."""

from __future__ import annotations

from typing import Optional

from ..database import AsyncSessionLocal
from ..models import SmsLog


async def record_sms_log(
    *,
    recipient_phone: str,
    message_preview: str,
    success: bool,
    message_type: str = "custom",
    recipient_name: Optional[str] = None,
    worker_id: Optional[int] = None,
    error: Optional[str] = None,
    provider_message_id: Optional[str] = None,
) -> None:
    preview = (message_preview or "")[:500]
    async with AsyncSessionLocal() as db:
        db.add(SmsLog(
            recipient_name=recipient_name,
            recipient_phone=recipient_phone,
            worker_id=worker_id,
            message_type=message_type or "custom",
            message_preview=preview,
            success=bool(success),
            error=error,
            provider_message_id=provider_message_id,
        ))
        await db.commit()
