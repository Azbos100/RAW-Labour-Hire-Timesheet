"""
RAW Labour Hire - Notifications API
Handles SMS reminders for clock in/out
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from pydantic import BaseModel
from datetime import datetime, date, time, timedelta
from typing import Optional, List

from ..database import get_db
from ..models import User, TimesheetEntry, NotificationSettings
from ..services.sms import (
    send_sms,
    clock_in_reminder_message,
    clock_out_reminder_message,
    timesheet_approved_message,
    timesheet_rejected_message
)

router = APIRouter()


@router.get("/test-sms/{phone}")
async def test_sms(phone: str):
    """Test SMS sending - debug endpoint"""
    from ..services.sms import send_sms, format_phone_number, TWILIO_ACCOUNT_SID, TWILIO_PHONE_NUMBER
    
    formatted = format_phone_number(phone)
    
    result = await send_sms(phone, "Test message from RAW Labour Hire")
    
    return {
        "original_phone": phone,
        "formatted_phone": formatted,
        "twilio_configured": bool(TWILIO_ACCOUNT_SID),
        "twilio_from_number": TWILIO_PHONE_NUMBER,
        "result": result
    }


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
            "sms_enabled": True
        }
    
    return {
        "clock_in_reminder_enabled": settings.clock_in_reminder_enabled,
        "clock_in_reminder_time": settings.clock_in_reminder_time.strftime("%H:%M") if settings.clock_in_reminder_time else "07:00",
        "clock_out_reminder_enabled": settings.clock_out_reminder_enabled,
        "clock_out_reminder_time": settings.clock_out_reminder_time.strftime("%H:%M") if settings.clock_out_reminder_time else "17:00",
        "sms_enabled": settings.sms_enabled
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
    
    if not settings:
        settings = NotificationSettings(
            clock_in_reminder_enabled=data.clock_in_reminder_enabled,
            clock_in_reminder_time=clock_in_time,
            clock_out_reminder_enabled=data.clock_out_reminder_enabled,
            clock_out_reminder_time=clock_out_time,
            sms_enabled=data.sms_enabled
        )
        db.add(settings)
    else:
        settings.clock_in_reminder_enabled = data.clock_in_reminder_enabled
        settings.clock_in_reminder_time = clock_in_time
        settings.clock_out_reminder_enabled = data.clock_out_reminder_enabled
        settings.clock_out_reminder_time = clock_out_time
        settings.sms_enabled = data.sms_enabled
    
    await db.commit()
    
    # Update the scheduler with new times
    try:
        from ..services.scheduler import update_clock_in_time, update_clock_out_time
        update_clock_in_time(clock_in_time.hour, clock_in_time.minute)
        update_clock_out_time(clock_out_time.hour, clock_out_time.minute)
    except Exception as e:
        print(f"[Notifications] Error updating scheduler: {e}")
    
    return {"message": "Settings updated successfully"}


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
    
    sms_result = await send_sms(worker.phone, data.message)
    
    if sms_result["success"]:
        return {"message": "SMS sent successfully", "to": worker.phone}
    else:
        raise HTTPException(status_code=500, detail=sms_result.get("error", "Failed to send SMS"))


# ==================== SCHEDULED REMINDER ENDPOINTS ====================
# These should be called by a cron job or scheduler

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
    
    # Get current time in Sydney timezone
    sydney_tz = pytz.timezone('Australia/Sydney')
    now = dt.now(sydney_tz)
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
        
        # Check if worker should work today
        if not worker_should_work_today(worker, today):
            skipped_count += 1
            continue
        
        # Check if worker's shift has started
        if not worker_shift_started(worker, current_time):
            skipped_count += 1
            continue
        
        # Check if worker has clocked in today
        entry_result = await db.execute(
            select(TimesheetEntry).where(
                and_(
                    TimesheetEntry.user_id == worker.id,
                    TimesheetEntry.entry_date == today,
                    TimesheetEntry.clock_in_time != None
                )
            )
        )
        has_clocked_in = entry_result.scalar_one_or_none() is not None
        
        if not has_clocked_in:
            # Send reminder
            message = clock_in_reminder_message(worker.first_name)
            result = await send_sms(worker.phone, message)
            
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
    
    # Get current time in Sydney timezone
    sydney_tz = pytz.timezone('Australia/Sydney')
    now = dt.now(sydney_tz)
    today = now.date()
    current_time = now.time()
    
    # Get all timesheet entries for today that have clock-in but no clock-out
    entries_result = await db.execute(
        select(TimesheetEntry, User)
        .join(User, TimesheetEntry.user_id == User.id)
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
        result = await send_sms(worker.phone, message)
        
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
    
    sms_result = await send_sms(worker.phone, message)
    
    return {
        "message": "Notification sent" if sms_result["success"] else "Failed to send",
        "sent": sms_result["success"],
        "error": sms_result.get("error")
    }
