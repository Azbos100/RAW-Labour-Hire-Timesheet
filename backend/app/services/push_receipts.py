"""Self-healing push delivery: clear dead Expo tokens and verify receipts.

Push is fire-and-forget, so "was it received?" can't be known for certain. What
we CAN do is detect when a token is permanently invalid (DeviceNotRegistered) —
either immediately from the send ticket, or later from the delivery receipt — and
clear it so the next notification falls back to SMS (and the app re-registers a
fresh token on its next launch).
"""

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select

from .push_notifications import (
    is_dead_token_result,
    ticket_error_code,
    ticket_id,
    get_push_receipts,
    DEAD_TOKEN_ERRORS,
)


async def _clear_token(user_id: int) -> None:
    """Null a user's push_token in its own short transaction (so we never disturb
    a caller's in-flight session)."""
    from ..database import AsyncSessionLocal
    from ..models import User

    async with AsyncSessionLocal() as s:
        u = (await s.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        if u and u.push_token:
            u.push_token = None
            await s.commit()


async def _record_receipt(ticket: str, user_id: Optional[int]) -> None:
    from ..database import AsyncSessionLocal
    from ..models import PushReceipt

    async with AsyncSessionLocal() as s:
        s.add(PushReceipt(ticket_id=ticket, user_id=user_id))
        await s.commit()


async def handle_push_result(user, push_result) -> None:
    """Call right after send_push_notification(). If the token is dead, clear it
    (and blank it on the in-memory object so the current flow falls back to SMS);
    otherwise record the receipt id for later verification."""
    result = (push_result or {}).get("result")
    uid = getattr(user, "id", None)

    if is_dead_token_result(push_result):
        print(f"[Push] Dead token for user {uid}: {ticket_error_code(result)} — clearing")
        if uid is not None:
            await _clear_token(uid)
        if hasattr(user, "push_token"):
            user.push_token = None  # so the caller's push-first check now fails -> SMS
        return

    tid = ticket_id(result)
    if tid and uid is not None:
        await _record_receipt(tid, uid)


async def check_pending_receipts() -> dict:
    """Scheduler job: verify receipts for tickets sent >15 min ago and clear any
    token Expo reports as permanently invalid. Processed rows are deleted."""
    from ..database import AsyncSessionLocal
    from ..models import PushReceipt, User

    ready_cutoff = datetime.utcnow() - timedelta(minutes=15)
    stale_cutoff = datetime.utcnow() - timedelta(hours=24)
    cleared = 0
    processed = 0

    async with AsyncSessionLocal() as s:
        rows = (await s.execute(
            select(PushReceipt)
            .where(PushReceipt.created_at <= ready_cutoff)
            .limit(500)
        )).scalars().all()
        if not rows:
            return {"processed": 0, "cleared": 0}

        by_ticket = {r.ticket_id: r for r in rows}
        receipts = await get_push_receipts(list(by_ticket.keys()))

        for tid, row in by_ticket.items():
            rec = receipts.get(tid) if isinstance(receipts, dict) else None
            if rec is None:
                # Receipt not ready yet — keep it for a later run unless it's ancient.
                if row.created_at and row.created_at < stale_cutoff:
                    await s.delete(row)
                continue
            if isinstance(rec, dict) and rec.get("status") == "error":
                err = (rec.get("details") or {}).get("error")
                if err in DEAD_TOKEN_ERRORS and row.user_id:
                    u = (await s.execute(
                        select(User).where(User.id == row.user_id)
                    )).scalar_one_or_none()
                    if u and u.push_token:
                        u.push_token = None
                        cleared += 1
            await s.delete(row)
            processed += 1

        await s.commit()

    if processed:
        print(f"[Scheduler] Push receipts checked: {processed} processed, {cleared} dead token(s) cleared")
    return {"processed": processed, "cleared": cleared}
