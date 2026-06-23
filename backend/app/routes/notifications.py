"""
RAW Labour Hire - Notifications API
Handles SMS reminders for clock in/out
"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from pydantic import BaseModel
from datetime import datetime, date, time, timedelta
from typing import Optional, List

from ..database import get_db
from ..models import User, Timesheet, TimesheetEntry, NotificationSettings, ClientContact, Client, SmsLog
from ..services.sms import (
    send_sms,
    format_phone_number,
    brand_message,
    clock_in_reminder_message,
    clock_out_reminder_message,
    timesheet_approved_message,
    timesheet_rejected_message
)

router = APIRouter()


@router.get("/test-sms/{phone}")
async def test_sms(phone: str):
    """Test SMS sending - debug endpoint"""
    from ..services.sms import send_sms, format_phone_number, TWILIO_ACCOUNT_SID, TWILIO_PHONE_NUMBER, get_sender
    
    formatted = format_phone_number(phone)
    
    result = await send_sms(phone, "Test message from RAW Labour Hire", message_type="test")
    
    return {
        "original_phone": phone,
        "formatted_phone": formatted,
        "twilio_configured": bool(TWILIO_ACCOUNT_SID),
        "twilio_from_number": TWILIO_PHONE_NUMBER,
        "twilio_sender": get_sender(),
        "result": result
    }


@router.get("/push-token-status")
async def get_push_token_status(db: AsyncSession = Depends(get_db)):
    """Debug endpoint to check which workers have push tokens registered"""
    try:
        result = await db.execute(
            select(User).where(User.is_active == True)
        )
        workers = result.scalars().all()
        
        with_token = []
        without_token = []
        
        for w in workers:
            try:
                full_name = f"{w.first_name or ''} {w.surname or ''}".strip() or "Unknown"
                worker_info = {
                    "id": w.id,
                    "name": full_name,
                    "email": w.email,
                    "phone": w.phone
                }
                if w.push_token:
                    with_token.append({**worker_info, "token_prefix": w.push_token[:30] + "..." if len(w.push_token) >= 30 else w.push_token})
                else:
                    without_token.append(worker_info)
            except Exception as worker_err:
                without_token.append({"id": w.id, "name": f"Error: {str(worker_err)}", "phone": None, "email": None})
        
        return {
            "total_workers": len(workers),
            "with_push_token": len(with_token),
            "without_push_token": len(without_token),
            "workers_with_tokens": with_token,
            "workers_without_tokens": without_token
        }
    except Exception as e:
        return {"error": str(e)}


@router.get("/scheduler-status")
async def get_scheduler_status():
    """Get the status of scheduled reminder jobs"""
    try:
        from ..services.scheduler import scheduler
        
        jobs = []
        for job in scheduler.get_jobs():
            next_run = job.next_run_time
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": next_run.isoformat() if next_run else None,
                "next_run_formatted": next_run.strftime("%a %d %b %Y at %I:%M %p AEST") if next_run else "Not scheduled"
            })
        
        return {
            "running": scheduler.running,
            "jobs": jobs
        }
    except Exception as e:
        return {
            "running": False,
            "error": str(e)
        }


class NotificationSettingsUpdate(BaseModel):
    clock_in_reminder_enabled: bool = True
    clock_in_reminder_time: str = "07:00"  # HH:MM format
    clock_out_reminder_enabled: bool = True
    clock_out_reminder_time: str = "17:00"  # HH:MM format
    sms_enabled: bool = True
    # Unaccepted-jobs notice (Mon-Fri)
    allocation_notice_enabled: bool = True
    allocation_notice_time: str = "18:15"
    allocation_notice_recipient_ids: List[int] = []
    allocation_notice_extra_phones: Optional[str] = None
    # Daily roster digest (every day)
    roster_digest_enabled: bool = True
    roster_digest_time: str = "19:00"
    roster_digest_recipient_ids: List[int] = []
    roster_digest_extra_phones: Optional[str] = None


def _ids_to_csv(ids) -> Optional[str]:
    if not ids:
        return None
    return ",".join(str(int(i)) for i in ids)


def _csv_to_ids(value) -> List[int]:
    if not value:
        return []
    out = []
    for part in str(value).split(","):
        part = part.strip()
        if part:
            try:
                out.append(int(part))
            except ValueError:
                pass
    return out


class SendSMSRequest(BaseModel):
    worker_id: int
    message: str


# ==================== ADMIN ENDPOINTS ====================

@router.get("/settings")
async def get_notification_settings(
    db: AsyncSession = Depends(get_db)
):
    """Get global notification settings"""
    result = await db.execute(select(NotificationSettings).limit(1))
    settings = result.scalar_one_or_none()
    
    if not settings:
        # Return defaults
        return {
            "clock_in_reminder_enabled": True,
            "clock_in_reminder_time": "07:00",
            "clock_out_reminder_enabled": True,
            "clock_out_reminder_time": "17:00",
            "sms_enabled": True,
            "allocation_notice_enabled": True,
            "allocation_notice_time": "18:15",
            "allocation_notice_recipient_ids": [],
            "allocation_notice_extra_phones": "",
            "roster_digest_enabled": True,
            "roster_digest_time": "19:00",
            "roster_digest_recipient_ids": [],
            "roster_digest_extra_phones": "",
        }
    
    return {
        "clock_in_reminder_enabled": settings.clock_in_reminder_enabled,
        "clock_in_reminder_time": settings.clock_in_reminder_time.strftime("%H:%M") if settings.clock_in_reminder_time else "07:00",
        "clock_out_reminder_enabled": settings.clock_out_reminder_enabled,
        "clock_out_reminder_time": settings.clock_out_reminder_time.strftime("%H:%M") if settings.clock_out_reminder_time else "17:00",
        "sms_enabled": settings.sms_enabled,
        "allocation_notice_enabled": settings.allocation_notice_enabled,
        "allocation_notice_time": settings.allocation_notice_time.strftime("%H:%M") if settings.allocation_notice_time else "18:15",
        "allocation_notice_recipient_ids": _csv_to_ids(settings.allocation_notice_recipient_ids),
        "allocation_notice_extra_phones": settings.allocation_notice_extra_phones or "",
        "roster_digest_enabled": settings.roster_digest_enabled if settings.roster_digest_enabled is not None else True,
        "roster_digest_time": settings.roster_digest_time.strftime("%H:%M") if settings.roster_digest_time else "19:00",
        "roster_digest_recipient_ids": _csv_to_ids(settings.roster_digest_recipient_ids),
        "roster_digest_extra_phones": settings.roster_digest_extra_phones or "",
    }


@router.post("/settings")
async def update_notification_settings(
    data: NotificationSettingsUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update global notification settings"""
    result = await db.execute(select(NotificationSettings).limit(1))
    settings = result.scalar_one_or_none()
    
    # Parse times
    clock_in_time = datetime.strptime(data.clock_in_reminder_time, "%H:%M").time()
    clock_out_time = datetime.strptime(data.clock_out_reminder_time, "%H:%M").time()
    allocation_time = datetime.strptime(data.allocation_notice_time, "%H:%M").time()
    roster_time = datetime.strptime(data.roster_digest_time, "%H:%M").time()
    allocation_ids_csv = _ids_to_csv(data.allocation_notice_recipient_ids)
    roster_ids_csv = _ids_to_csv(data.roster_digest_recipient_ids)
    
    if not settings:
        settings = NotificationSettings(
            clock_in_reminder_enabled=data.clock_in_reminder_enabled,
            clock_in_reminder_time=clock_in_time,
            clock_out_reminder_enabled=data.clock_out_reminder_enabled,
            clock_out_reminder_time=clock_out_time,
            sms_enabled=data.sms_enabled,
        )
        db.add(settings)
    else:
        settings.clock_in_reminder_enabled = data.clock_in_reminder_enabled
        settings.clock_in_reminder_time = clock_in_time
        settings.clock_out_reminder_enabled = data.clock_out_reminder_enabled
        settings.clock_out_reminder_time = clock_out_time
        settings.sms_enabled = data.sms_enabled

    # Unaccepted-jobs notice
    settings.allocation_notice_enabled = data.allocation_notice_enabled
    settings.allocation_notice_time = allocation_time
    settings.allocation_notice_recipient_ids = allocation_ids_csv
    settings.allocation_notice_extra_phones = (data.allocation_notice_extra_phones or "").strip() or None
    # Daily roster digest
    settings.roster_digest_enabled = data.roster_digest_enabled
    settings.roster_digest_time = roster_time
    settings.roster_digest_recipient_ids = roster_ids_csv
    settings.roster_digest_extra_phones = (data.roster_digest_extra_phones or "").strip() or None
    
    await db.commit()
    
    # Update the scheduler with new times
    try:
        from ..services.scheduler import (
            update_clock_in_time, update_clock_out_time,
            update_allocation_notice_time, update_roster_digest_time,
        )
        update_clock_in_time(clock_in_time.hour, clock_in_time.minute)
        update_clock_out_time(clock_out_time.hour, clock_out_time.minute)
        update_allocation_notice_time(allocation_time.hour, allocation_time.minute)
        update_roster_digest_time(roster_time.hour, roster_time.minute)
    except Exception as e:
        print(f"[Notifications] Error updating scheduler: {e}")
    
    return {"message": "Settings updated successfully"}


@router.get("/sms-log")
async def get_sms_log(
    limit: int = 100,
    offset: int = 0,
    message_type: Optional[str] = None,
    worker_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Admin audit trail of outbound SMS messages."""
    from sqlalchemy import func

    limit = max(1, min(limit, 500))
    offset = max(0, offset)

    query = select(SmsLog).order_by(SmsLog.sent_at.desc())
    count_query = select(func.count(SmsLog.id))

    if message_type:
        query = query.where(SmsLog.message_type == message_type)
        count_query = count_query.where(SmsLog.message_type == message_type)
    if worker_id:
        query = query.where(SmsLog.worker_id == worker_id)
        count_query = count_query.where(SmsLog.worker_id == worker_id)
    if date_from:
        try:
            d_from = datetime.strptime(date_from, "%Y-%m-%d")
            query = query.where(SmsLog.sent_at >= d_from)
            count_query = count_query.where(SmsLog.sent_at >= d_from)
        except ValueError:
            pass
    if date_to:
        try:
            d_to = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            query = query.where(SmsLog.sent_at < d_to)
            count_query = count_query.where(SmsLog.sent_at < d_to)
        except ValueError:
            pass

    total = (await db.execute(count_query)).scalar() or 0
    rows = (await db.execute(query.offset(offset).limit(limit))).scalars().all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "logs": [
            {
                "id": r.id,
                "sent_at": r.sent_at.isoformat() if r.sent_at else None,
                "recipient_name": r.recipient_name,
                "recipient_phone": r.recipient_phone,
                "worker_id": r.worker_id,
                "message_type": r.message_type,
                "message_preview": r.message_preview,
                "success": r.success,
                "error": r.error,
            }
            for r in rows
        ],
    }


@router.delete("/sms-log/{log_id}")
async def delete_sms_log_entry(
    log_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Remove a single SMS log row from the admin audit trail."""
    result = await db.execute(select(SmsLog).where(SmsLog.id == log_id))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="SMS log entry not found")
    await db.delete(row)
    await db.commit()
    return {"message": "SMS log entry deleted", "id": log_id}


@router.post("/send-sms")
async def send_sms_to_worker(
    data: SendSMSRequest,
    db: AsyncSession = Depends(get_db)
):
    """Send a custom SMS to a worker (admin)"""
    result = await db.execute(select(User).where(User.id == data.worker_id))
    worker = result.scalar_one_or_none()
    
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    
    if not worker.phone:
        raise HTTPException(status_code=400, detail="Worker has no phone number")
    
    sms_result = await send_sms(
        worker.phone,
        brand_message(data.message),
        recipient_name=f"{worker.first_name} {worker.surname}",
        worker_id=worker.id,
        message_type="custom",
    )
    
    if sms_result["success"]:
        return {"message": "SMS sent successfully", "to": worker.phone}
    else:
        raise HTTPException(status_code=500, detail=sms_result.get("error", "Failed to send SMS"))


class BroadcastSMSRequest(BaseModel):
    message: str
    phones: Optional[List[str]] = None  # if set, only send to these numbers


def _dedupe_foremen(rows):
    """Return [(name, formatted_phone, client_name)] with blank/duplicate phones removed."""
    seen = set()
    out = []
    for c, client_name in rows:
        if not c.phone:
            continue
        fp = format_phone_number(c.phone)
        if not fp or fp in seen:
            continue
        seen.add(fp)
        out.append((c.name, fp, client_name))
    return out


async def _foreman_rows(db: AsyncSession):
    result = await db.execute(
        select(ClientContact, Client.name)
        .join(Client, ClientContact.client_id == Client.id)
        .where(ClientContact.is_active == True)
    )
    return result.all()


@router.get("/foremen")
async def list_foremen(db: AsyncSession = Depends(get_db)):
    """List active foremen / site contacts who have a phone number (deduped)."""
    recipients = _dedupe_foremen(await _foreman_rows(db))
    return {
        "count": len(recipients),
        "foremen": [{"name": n, "phone": p, "client_name": cn} for n, p, cn in recipients],
    }


@router.post("/broadcast-foremen")
async def broadcast_to_foremen(
    data: BroadcastSMSRequest,
    db: AsyncSession = Depends(get_db)
):
    """Send a one-off SMS to selected (or all) active foremen / site contacts."""
    if not (data.message or "").strip():
        raise HTTPException(status_code=400, detail="Message is empty")
    message = brand_message((data.message or "").strip())

    recipients = _dedupe_foremen(await _foreman_rows(db))

    # If specific phone numbers were chosen, filter to those
    if data.phones:
        wanted = {format_phone_number(p) for p in data.phones if p}
        recipients = [r for r in recipients if r[1] in wanted]

    if not recipients:
        raise HTTPException(status_code=400, detail="No foremen with phone numbers found")

    sent = 0
    failed = 0
    errors = []
    for name, phone, _client_name in recipients:
        res = await send_sms(
            phone,
            message,
            recipient_name=name,
            message_type="foremen_broadcast",
        )
        if res.get("success"):
            sent += 1
        else:
            failed += 1
            errors.append(f"{name}: {res.get('error', 'failed')}")

    return {
        "sent": sent,
        "failed": failed,
        "total": len(recipients),
        "errors": errors[:10],
    }


# ==================== SCHEDULED REMINDER ENDPOINTS ====================
# These should be called by a cron job or scheduler

def worker_assigned_today(worker, today: date) -> bool:
    """True if the worker has a job assigned for `today` and hasn't declined it.

    This is what gates clock-in reminders: we only nudge people who actually have
    a job on, not every idle worker on the books.
    """
    return (
        worker.assigned_job_site_id is not None
        and worker.assignment_date == today
        and worker.assignment_accepted is not False  # skip explicitly declined jobs
    )


def worker_should_work_today(worker, today: date) -> bool:
    """Check if worker is scheduled to work today based on their schedule"""
    day_of_week = today.weekday()  # 0=Monday, 6=Sunday
    day_map = {
        0: worker.works_monday,
        1: worker.works_tuesday,
        2: worker.works_wednesday,
        3: worker.works_thursday,
        4: worker.works_friday,
        5: worker.works_saturday,
        6: worker.works_sunday
    }
    # Default to True if not set (backwards compatibility)
    works_today = day_map.get(day_of_week)
    return works_today if works_today is not None else True


def worker_shift_started(worker, current_time: time) -> bool:
    """Check if worker's shift should have started by now"""
    if not worker.shift_start_time:
        return True  # No shift time set, assume they should be working
    return current_time >= worker.shift_start_time


def worker_shift_ended(worker, current_time: time) -> bool:
    """Check if worker's shift should have ended by now"""
    if not worker.shift_end_time:
        return True  # No shift time set, assume shift ended
    return current_time >= worker.shift_end_time


@router.post("/check-clock-in-reminders")
async def check_clock_in_reminders(
    db: AsyncSession = Depends(get_db)
):
    """
    Check for workers who haven't clocked in and send reminders.
    Only sends to workers whose shift has started based on their individual schedule.
    """
    import pytz
    from datetime import datetime as dt
    
    # Get notification settings
    settings_result = await db.execute(select(NotificationSettings).limit(1))
    settings = settings_result.scalar_one_or_none()
    
    if settings and not settings.clock_in_reminder_enabled:
        return {"message": "Clock-in reminders disabled", "sent": 0}
    
    if settings and not settings.sms_enabled:
        return {"message": "SMS notifications disabled", "sent": 0}
    
    # Get current time in Melbourne timezone
    melbourne_tz = pytz.timezone('Australia/Melbourne')
    now = dt.now(melbourne_tz)
    today = now.date()
    current_time = now.time()
    
    # Get all active workers
    workers_result = await db.execute(
        select(User).where(User.is_active == True)
    )
    workers = workers_result.scalars().all()
    
    sent_count = 0
    skipped_count = 0
    errors = []
    
    for worker in workers:
        if not worker.phone:
            continue
        
        # Only remind workers who actually have a job assigned for today (and who
        # haven't declined it). This stops idle/unassigned workers being texted.
        if not worker_assigned_today(worker, today):
            skipped_count += 1
            continue
        
        # Check if worker has clocked in today
        entry_result = await db.execute(
            select(TimesheetEntry)
            .join(Timesheet, TimesheetEntry.timesheet_id == Timesheet.id)
            .where(
                and_(
                    Timesheet.worker_id == worker.id,
                    TimesheetEntry.entry_date == today,
                    TimesheetEntry.clock_in_time != None
                )
            )
        )
        has_clocked_in = entry_result.scalar_one_or_none() is not None
        
        if not has_clocked_in:
            # Send reminder
            message = clock_in_reminder_message(worker.first_name)
            result = await send_sms(
                worker.phone,
                message,
                recipient_name=f"{worker.first_name} {worker.surname}",
                worker_id=worker.id,
                message_type="clock_in_reminder",
            )
            
            if result["success"]:
                sent_count += 1
            else:
                errors.append({
                    "worker": f"{worker.first_name} {worker.surname}",
                    "error": result.get("error")
                })
    
    return {
        "message": f"Clock-in reminders sent",
        "sent": sent_count,
        "skipped": skipped_count,
        "errors": errors if errors else None
    }


@router.post("/check-clock-out-reminders")
async def check_clock_out_reminders(
    db: AsyncSession = Depends(get_db)
):
    """
    Check for workers who clocked in but haven't clocked out and send reminders.
    Only sends to workers whose shift has ended based on their individual schedule.
    """
    import pytz
    from datetime import datetime as dt
    
    # Get notification settings
    settings_result = await db.execute(select(NotificationSettings).limit(1))
    settings = settings_result.scalar_one_or_none()
    
    if settings and not settings.clock_out_reminder_enabled:
        return {"message": "Clock-out reminders disabled", "sent": 0}
    
    if settings and not settings.sms_enabled:
        return {"message": "SMS notifications disabled", "sent": 0}
    
    # Get current time in Melbourne timezone
    melbourne_tz = pytz.timezone('Australia/Melbourne')
    now = dt.now(melbourne_tz)
    today = now.date()
    current_time = now.time()
    
    # Get all timesheet entries for today that have clock-in but no clock-out
    entries_result = await db.execute(
        select(TimesheetEntry, User)
        .join(Timesheet, TimesheetEntry.timesheet_id == Timesheet.id)
        .join(User, Timesheet.worker_id == User.id)
        .where(
            and_(
                TimesheetEntry.entry_date == today,
                TimesheetEntry.clock_in_time != None,
                TimesheetEntry.clock_out_time == None,
                User.is_active == True
            )
        )
    )
    entries = entries_result.all()
    
    sent_count = 0
    skipped_count = 0
    errors = []
    
    for entry, worker in entries:
        if not worker.phone:
            continue
        
        # Skip workers in overtime mode - they're staying back intentionally
        if entry.overtime_mode:
            skipped_count += 1
            continue
        
        # Check if worker's shift has ended
        if not worker_shift_ended(worker, current_time):
            skipped_count += 1
            continue
        
        # Send reminder
        message = clock_out_reminder_message(worker.first_name)
        result = await send_sms(
            worker.phone,
            message,
            recipient_name=f"{worker.first_name} {worker.surname}",
            worker_id=worker.id,
            message_type="clock_out_reminder",
        )
        
        if result["success"]:
            sent_count += 1
        else:
            errors.append({
                "worker": f"{worker.first_name} {worker.surname}",
                "error": result.get("error")
            })
    
    return {
        "message": f"Clock-out reminders sent",
        "sent": sent_count,
        "skipped": skipped_count,
        "errors": errors if errors else None
    }


@router.post("/send-timesheet-notification")
async def send_timesheet_notification(
    timesheet_id: int,
    notification_type: str,  # "approved" or "rejected"
    db: AsyncSession = Depends(get_db)
):
    """Send notification when timesheet is approved/rejected"""
    from ..models import Timesheet
    
    result = await db.execute(
        select(Timesheet, User)
        .join(User, Timesheet.worker_id == User.id)
        .where(Timesheet.id == timesheet_id)
    )
    row = result.one_or_none()
    
    if not row:
        raise HTTPException(status_code=404, detail="Timesheet not found")
    
    timesheet, worker = row
    
    if not worker.phone:
        return {"message": "Worker has no phone number", "sent": False}
    
    if notification_type == "approved":
        message = timesheet_approved_message(worker.first_name, timesheet.docket_number)
    elif notification_type == "rejected":
        message = timesheet_rejected_message(worker.first_name, timesheet.docket_number)
    else:
        raise HTTPException(status_code=400, detail="Invalid notification type")
    
    sms_result = await send_sms(
        worker.phone,
        message,
        recipient_name=f"{worker.first_name} {worker.surname}",
        worker_id=worker.id,
        message_type=f"timesheet_{notification_type}",
    )
    
    return {
        "message": "Notification sent" if sms_result["success"] else "Failed to send",
        "sent": sms_result["success"],
        "error": sms_result.get("error")
    }
