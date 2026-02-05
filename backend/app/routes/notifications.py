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

@router.post("/check-clock-in-reminders")
async def check_clock_in_reminders(
    db: AsyncSession = Depends(get_db)
):
    """
    Check for workers who haven't clocked in and send reminders.
    Call this endpoint via cron job at the reminder time (e.g., 7:00 AM)
    """
    # Get notification settings
    settings_result = await db.execute(select(NotificationSettings).limit(1))
    settings = settings_result.scalar_one_or_none()
    
    if settings and not settings.clock_in_reminder_enabled:
        return {"message": "Clock-in reminders disabled", "sent": 0}
    
    if settings and not settings.sms_enabled:
        return {"message": "SMS notifications disabled", "sent": 0}
    
    today = date.today()
    
    # Get all active workers
    workers_result = await db.execute(
        select(User).where(User.is_active == True)
    )
    workers = workers_result.scalars().all()
    
    sent_count = 0
    errors = []
    
    for worker in workers:
        if not worker.phone:
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
        "errors": errors if errors else None
    }


@router.post("/check-clock-out-reminders")
async def check_clock_out_reminders(
    db: AsyncSession = Depends(get_db)
):
    """
    Check for workers who clocked in but haven't clocked out and send reminders.
    Call this endpoint via cron job at the reminder time (e.g., 5:00 PM)
    """
    # Get notification settings
    settings_result = await db.execute(select(NotificationSettings).limit(1))
    settings = settings_result.scalar_one_or_none()
    
    if settings and not settings.clock_out_reminder_enabled:
        return {"message": "Clock-out reminders disabled", "sent": 0}
    
    if settings and not settings.sms_enabled:
        return {"message": "SMS notifications disabled", "sent": 0}
    
    today = date.today()
    
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
    errors = []
    
    for entry, worker in entries:
        if not worker.phone:
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
