"""
RAW Labour Hire - Timesheets API
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from datetime import datetime, date, timedelta
from typing import Optional, List

from ..database import get_db
from ..models import User, Timesheet, TimesheetEntry, TimesheetStatus, InjuryStatus, Client
from .auth import get_current_user

router = APIRouter()


# ==================== ADMIN DASHBOARD ENDPOINTS ====================

@router.get("/admin/all")
async def get_all_timesheets_admin(
    status: Optional[str] = None,
    worker_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get all timesheets for admin dashboard (no auth required)"""
    query = select(Timesheet).order_by(Timesheet.week_starting.desc())
    
    if status:
        query = query.where(Timesheet.status == TimesheetStatus(status))
    if worker_id:
        query = query.where(Timesheet.worker_id == worker_id)
    
    result = await db.execute(query)
    timesheets = result.scalars().all()
    
    # Get worker and client names
    response_data = []
    for ts in timesheets:
        # Get worker
        worker_result = await db.execute(select(User).where(User.id == ts.worker_id))
        worker = worker_result.scalar_one_or_none()
        
        # Get client
        client_result = await db.execute(select(Client).where(Client.id == ts.client_id))
        client = client_result.scalar_one_or_none()
        
        response_data.append({
            "id": ts.id,
            "docket_number": ts.docket_number,
            "worker_id": ts.worker_id,
            "worker_name": f"{worker.first_name} {worker.surname}" if worker else "Unknown",
            "client_id": ts.client_id,
            "client_name": client.name if client else None,
            "week_starting": ts.week_starting.isoformat(),
            "week_ending": ts.week_ending.isoformat(),
            "status": ts.status.value,
            "total_ordinary_hours": ts.total_ordinary_hours or 0,
            "total_overtime_hours": ts.total_overtime_hours or 0,
            "total_hours": ts.total_hours or 0,
            "supervisor_name": ts.supervisor_name,
            "supervisor_contact": ts.supervisor_contact,
            "supervisor_signature": ts.supervisor_signature,
            "submitted_at": ts.submitted_at.isoformat() if ts.submitted_at else None,
        })
    
    return {"timesheets": response_data}


@router.post("/{timesheet_id}/approve")
async def approve_timesheet(
    timesheet_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Approve a timesheet (admin)"""
    result = await db.execute(select(Timesheet).where(Timesheet.id == timesheet_id))
    timesheet = result.scalar_one_or_none()
    
    if not timesheet:
        raise HTTPException(status_code=404, detail="Timesheet not found")
    
    if timesheet.status != TimesheetStatus.SUBMITTED:
        raise HTTPException(status_code=400, detail="Timesheet must be submitted to approve")
    
    timesheet.status = TimesheetStatus.APPROVED
    await db.commit()
    
    return {"message": "Timesheet approved", "status": "approved"}


class RejectRequest(BaseModel):
    reason: Optional[str] = None


@router.post("/{timesheet_id}/reject")
async def reject_timesheet(
    timesheet_id: int,
    data: RejectRequest = None,
    db: AsyncSession = Depends(get_db)
):
    """Reject a timesheet (admin)"""
    result = await db.execute(select(Timesheet).where(Timesheet.id == timesheet_id))
    timesheet = result.scalar_one_or_none()
    
    if not timesheet:
        raise HTTPException(status_code=404, detail="Timesheet not found")
    
    timesheet.status = TimesheetStatus.REJECTED
    await db.commit()
    
    return {"message": "Timesheet rejected", "status": "rejected"}


class TimesheetResponse(BaseModel):
    id: int
    docket_number: str
    week_starting: date
    week_ending: date
    status: str
    total_ordinary_hours: float
    total_overtime_hours: float
    total_hours: float
    client_name: Optional[str] = None
    entries: List[dict] = []


class SubmitTimesheetRequest(BaseModel):
    company_name: str
    supervisor_name: str
    supervisor_contact: str
    supervisor_signature: Optional[str] = None  # Base64 encoded signature image
    injury_reported: str = "n/a"  # yes, no, n/a


class SubmitEntryRequest(BaseModel):
    company_name: str
    supervisor_name: str
    supervisor_contact: str
    supervisor_signature: Optional[str] = None  # Base64 encoded signature image


@router.get("/current")
async def get_current_timesheet(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get the current week's timesheet for the logged in worker"""
    today = date.today()
    # Get Monday of current week
    monday = today - timedelta(days=today.weekday())
    
    result = await db.execute(
        select(Timesheet)
        .where(
            Timesheet.worker_id == current_user.id,
            Timesheet.week_starting == monday
        )
    )
    timesheets = result.scalars().all()
    
    return {
        "timesheets": [
            {
                "id": ts.id,
                "docket_number": ts.docket_number,
                "week_starting": ts.week_starting.isoformat(),
                "week_ending": ts.week_ending.isoformat(),
                "status": ts.status.value,
                "total_hours": ts.total_hours
            }
            for ts in timesheets
        ]
    }


@router.get("/{timesheet_id}")
async def get_timesheet(
    timesheet_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific timesheet with all entries
    TODO: Re-add authentication once token issue is fixed.
    """
    result = await db.execute(
        select(Timesheet).where(Timesheet.id == timesheet_id)
    )
    timesheet = result.scalar_one_or_none()
    
    if not timesheet:
        raise HTTPException(status_code=404, detail="Timesheet not found")
    
    # Get entries
    result = await db.execute(
        select(TimesheetEntry)
        .where(TimesheetEntry.timesheet_id == timesheet_id)
        .order_by(TimesheetEntry.entry_date)
    )
    entries = result.scalars().all()
    
    return {
        "id": timesheet.id,
        "docket_number": timesheet.docket_number,
        "order_number": timesheet.order_number,
        "week_starting": timesheet.week_starting.isoformat(),
        "week_ending": timesheet.week_ending.isoformat(),
        "status": timesheet.status.value,
        "total_ordinary_hours": timesheet.total_ordinary_hours,
        "total_overtime_hours": timesheet.total_overtime_hours,
        "total_hours": timesheet.total_hours,
        "injury_reported": timesheet.injury_reported.value if timesheet.injury_reported else "n/a",
        "supervisor_signed_at": timesheet.supervisor_signed_at.isoformat() if timesheet.supervisor_signed_at else None,
        "entries": [
            {
                "id": e.id,
                "day_of_week": e.day_of_week,
                "entry_date": e.entry_date.isoformat(),
                "time_start": e.time_start.isoformat() if e.time_start else None,
                "time_finish": e.time_finish.isoformat() if e.time_finish else None,
                "clock_in_time": e.clock_in_time.isoformat() if e.clock_in_time else None,
                "clock_out_time": e.clock_out_time.isoformat() if e.clock_out_time else None,
                "ordinary_hours": e.ordinary_hours,
                "overtime_hours": e.overtime_hours,
                "total_hours": e.total_hours,
                "worked_as": e.worked_as,
                "comments": e.comments,
                "first_aid_injury": e.first_aid_injury,
                "clock_in_address": e.clock_in_address,
                "clock_out_address": e.clock_out_address,
                "entry_status": e.entry_status or "draft",
                "host_company_name": e.host_company_name,
                "supervisor_name": e.supervisor_name
            }
            for e in entries
        ]
    }


@router.post("/{timesheet_id}/submit")
async def submit_timesheet(
    timesheet_id: int,
    request: SubmitTimesheetRequest,
    db: AsyncSession = Depends(get_db)
):
    """Submit a timesheet for supervisor approval
    TODO: Re-add authentication once token issue is fixed.
    """
    result = await db.execute(
        select(Timesheet).where(Timesheet.id == timesheet_id)
    )
    timesheet = result.scalar_one_or_none()
    
    if not timesheet:
        raise HTTPException(status_code=404, detail="Timesheet not found")
    
    if timesheet.status != TimesheetStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Timesheet already submitted")
    
    # Get worker info for email
    worker_result = await db.execute(
        select(User).where(User.id == timesheet.worker_id)
    )
    worker = worker_result.scalar_one_or_none()
    worker_name = f"{worker.first_name} {worker.surname}" if worker else "Unknown"
    
    # Update timesheet
    timesheet.status = TimesheetStatus.SUBMITTED
    timesheet.submitted_at = datetime.utcnow()
    timesheet.host_company_name = request.company_name
    timesheet.supervisor_name = request.supervisor_name
    timesheet.supervisor_contact = request.supervisor_contact
    timesheet.supervisor_signature = request.supervisor_signature
    timesheet.supervisor_signed_at = datetime.utcnow()
    timesheet.injury_reported = InjuryStatus(request.injury_reported)
    
    await db.commit()
    
    # Send email notification
    try:
        await send_timesheet_notification(
            worker_name=worker_name,
            docket_number=timesheet.docket_number,
            company_name=request.company_name,
            supervisor_name=request.supervisor_name,
            supervisor_contact=request.supervisor_contact,
            week_starting=timesheet.week_starting.isoformat(),
            week_ending=timesheet.week_ending.isoformat(),
            total_hours=timesheet.total_hours,
        )
    except Exception as e:
        # Log error but don't fail the submission
        print(f"Failed to send email notification: {e}")
    
    return {
        "message": "Timesheet submitted for approval",
        "docket_number": timesheet.docket_number,
        "status": timesheet.status.value
    }


@router.post("/entries/{entry_id}/submit")
async def submit_entry(
    entry_id: int,
    request: SubmitEntryRequest,
    db: AsyncSession = Depends(get_db)
):
    """Submit an individual daily entry for approval"""
    result = await db.execute(
        select(TimesheetEntry).where(TimesheetEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    
    if entry.entry_status == "submitted":
        raise HTTPException(status_code=400, detail="Entry already submitted")
    
    # Update entry with submission details
    entry.entry_status = "submitted"
    entry.host_company_name = request.company_name
    entry.supervisor_name = request.supervisor_name
    entry.supervisor_contact = request.supervisor_contact
    entry.supervisor_signature = request.supervisor_signature
    entry.submitted_at = datetime.utcnow()
    
    await db.commit()
    
    return {
        "message": "Entry submitted for approval",
        "entry_id": entry.id,
        "entry_date": entry.entry_date.isoformat(),
        "status": entry.entry_status
    }


async def send_timesheet_notification(
    worker_name: str,
    docket_number: str,
    company_name: str,
    supervisor_name: str,
    supervisor_contact: str,
    week_starting: str,
    week_ending: str,
    total_hours: float,
):
    """Send email notification when timesheet is submitted"""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    import os
    
    smtp_host = os.getenv("SMTP_HOST", "smtp.office365.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "accounts@rawlabourhire.com")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    notification_email = os.getenv("NOTIFICATION_EMAIL", "accounts@rawlabourhire.com")
    
    if not smtp_password:
        print("SMTP password not configured, skipping email")
        return
    
    subject = f"Timesheet Submitted - {worker_name} - #{docket_number}"
    
    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <h2 style="color: #1E3A8A;">Timesheet Submission</h2>
        <p>A new timesheet has been submitted for approval.</p>
        
        <table style="border-collapse: collapse; width: 100%; max-width: 500px;">
            <tr>
                <td style="padding: 8px; border-bottom: 1px solid #ddd; font-weight: bold;">Docket Number:</td>
                <td style="padding: 8px; border-bottom: 1px solid #ddd;">#{docket_number}</td>
            </tr>
            <tr>
                <td style="padding: 8px; border-bottom: 1px solid #ddd; font-weight: bold;">Worker:</td>
                <td style="padding: 8px; border-bottom: 1px solid #ddd;">{worker_name}</td>
            </tr>
            <tr>
                <td style="padding: 8px; border-bottom: 1px solid #ddd; font-weight: bold;">Week:</td>
                <td style="padding: 8px; border-bottom: 1px solid #ddd;">{week_starting} to {week_ending}</td>
            </tr>
            <tr>
                <td style="padding: 8px; border-bottom: 1px solid #ddd; font-weight: bold;">Total Hours:</td>
                <td style="padding: 8px; border-bottom: 1px solid #ddd;">{total_hours:.1f} hours</td>
            </tr>
            <tr>
                <td style="padding: 8px; border-bottom: 1px solid #ddd; font-weight: bold;">Host Company:</td>
                <td style="padding: 8px; border-bottom: 1px solid #ddd;">{company_name}</td>
            </tr>
            <tr>
                <td style="padding: 8px; border-bottom: 1px solid #ddd; font-weight: bold;">Supervisor:</td>
                <td style="padding: 8px; border-bottom: 1px solid #ddd;">{supervisor_name}</td>
            </tr>
            <tr>
                <td style="padding: 8px; border-bottom: 1px solid #ddd; font-weight: bold;">Supervisor Contact:</td>
                <td style="padding: 8px; border-bottom: 1px solid #ddd;">{supervisor_contact}</td>
            </tr>
        </table>
        
        <p style="margin-top: 20px; color: #666; font-size: 12px;">
            This is an automated message from the RAW Labour Hire Timesheet App.
        </p>
    </body>
    </html>
    """
    
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = notification_email
    
    msg.attach(MIMEText(html_body, "html"))
    
    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_user, notification_email, msg.as_string())


@router.get("/")
async def list_timesheets(
    status: Optional[str] = None,
    limit: int = 20,
    user_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    """List timesheets for the current user
    TODO: Re-add authentication once token issue is fixed.
    """
    from sqlalchemy import func
    
    # Use provided user_id or fall back to first user
    if user_id:
        result = await db.execute(select(User).where(User.id == user_id))
    else:
        result = await db.execute(select(User).limit(1))
    current_user = result.scalar_one_or_none()
    if not current_user:
        return {"timesheets": []}
    
    query = select(Timesheet).where(Timesheet.worker_id == current_user.id)
    
    # For 'submitted' status, also include timesheets with submitted entries
    if status == 'submitted':
        # Get timesheets that are submitted OR have submitted entries
        subquery = select(TimesheetEntry.timesheet_id).where(
            TimesheetEntry.entry_status == 'submitted'
        ).distinct()
        query = select(Timesheet).where(
            Timesheet.worker_id == current_user.id,
            (Timesheet.status == TimesheetStatus.submitted) | (Timesheet.id.in_(subquery))
        )
    elif status == 'approved':
        # Get timesheets that are approved OR have approved entries
        subquery = select(TimesheetEntry.timesheet_id).where(
            TimesheetEntry.entry_status == 'approved'
        ).distinct()
        query = select(Timesheet).where(
            Timesheet.worker_id == current_user.id,
            (Timesheet.status == TimesheetStatus.approved) | (Timesheet.id.in_(subquery))
        )
    elif status:
        query = query.where(Timesheet.status == TimesheetStatus(status))
    
    query = query.order_by(Timesheet.week_starting.desc()).limit(limit)
    
    result = await db.execute(query)
    timesheets = result.scalars().all()
    
    # Get entry counts for each timesheet
    timesheet_data = []
    for ts in timesheets:
        # Count submitted entries
        entry_result = await db.execute(
            select(func.count(TimesheetEntry.id)).where(
                TimesheetEntry.timesheet_id == ts.id,
                TimesheetEntry.entry_status == 'submitted'
            )
        )
        submitted_entries = entry_result.scalar() or 0
        
        # Count approved entries
        approved_result = await db.execute(
            select(func.count(TimesheetEntry.id)).where(
                TimesheetEntry.timesheet_id == ts.id,
                TimesheetEntry.entry_status == 'approved'
            )
        )
        approved_entries = approved_result.scalar() or 0
        
        timesheet_data.append({
            "id": ts.id,
            "docket_number": ts.docket_number,
            "week_starting": ts.week_starting.isoformat(),
            "week_ending": ts.week_ending.isoformat(),
            "status": ts.status.value,
            "total_hours": ts.total_hours,
            "submitted_at": ts.submitted_at.isoformat() if ts.submitted_at else None,
            "submitted_entries_count": submitted_entries,
            "approved_entries_count": approved_entries
        })
    
    return {"timesheets": timesheet_data}


# Import timedelta for the get_current_timesheet function
from datetime import timedelta


# ============ ADMIN ENDPOINTS ============

@router.get("/admin/pending-entries")
async def get_pending_entries(
    db: AsyncSession = Depends(get_db)
):
    """Get all submitted entries pending approval (admin view)"""
    from sqlalchemy import func
    
    result = await db.execute(
        select(TimesheetEntry)
        .where(TimesheetEntry.entry_status == 'submitted')
        .order_by(TimesheetEntry.submitted_at.desc())
    )
    entries = result.scalars().all()
    
    # Get worker info for each entry
    entry_data = []
    for entry in entries:
        # Get timesheet and worker info
        ts_result = await db.execute(
            select(Timesheet).where(Timesheet.id == entry.timesheet_id)
        )
        timesheet = ts_result.scalar_one_or_none()
        
        worker = None
        if timesheet:
            worker_result = await db.execute(
                select(User).where(User.id == timesheet.worker_id)
            )
            worker = worker_result.scalar_one_or_none()
        
        entry_data.append({
            "id": entry.id,
            "timesheet_id": entry.timesheet_id,
            "docket_number": timesheet.docket_number if timesheet else None,
            "worker_name": f"{worker.first_name} {worker.surname}" if worker else "Unknown",
            "worker_email": worker.email if worker else None,
            "day_of_week": entry.day_of_week,
            "entry_date": entry.entry_date.isoformat(),
            "clock_in_time": entry.clock_in_time.isoformat() if entry.clock_in_time else None,
            "clock_out_time": entry.clock_out_time.isoformat() if entry.clock_out_time else None,
            "total_hours": entry.total_hours,
            "worked_as": entry.worked_as,
            "clock_in_address": entry.clock_in_address,
            "host_company_name": entry.host_company_name,
            "supervisor_name": entry.supervisor_name,
            "supervisor_contact": entry.supervisor_contact,
            "supervisor_signature": entry.supervisor_signature,
            "submitted_at": entry.submitted_at.isoformat() if entry.submitted_at else None,
        })
    
    return {"entries": entry_data}


@router.post("/admin/entries/{entry_id}/approve")
async def approve_entry(
    entry_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Approve a submitted entry"""
    result = await db.execute(
        select(TimesheetEntry).where(TimesheetEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    
    entry.entry_status = "approved"
    await db.commit()
    
    return {"message": "Entry approved", "entry_id": entry_id}


@router.post("/admin/entries/{entry_id}/reject")
async def reject_entry(
    entry_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Reject a submitted entry"""
    result = await db.execute(
        select(TimesheetEntry).where(TimesheetEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    
    entry.entry_status = "rejected"
    await db.commit()
    
    return {"message": "Entry rejected", "entry_id": entry_id}


@router.get("/admin/approved-entries")
async def get_approved_entries(
    db: AsyncSession = Depends(get_db)
):
    """Get all approved entries (admin view)"""
    result = await db.execute(
        select(TimesheetEntry)
        .where(TimesheetEntry.entry_status == 'approved')
        .order_by(TimesheetEntry.submitted_at.desc())
    )
    entries = result.scalars().all()
    
    # Get worker info for each entry
    entry_data = []
    for entry in entries:
        # Get timesheet and worker info
        ts_result = await db.execute(
            select(Timesheet).where(Timesheet.id == entry.timesheet_id)
        )
        timesheet = ts_result.scalar_one_or_none()
        
        worker = None
        if timesheet:
            worker_result = await db.execute(
                select(User).where(User.id == timesheet.worker_id)
            )
            worker = worker_result.scalar_one_or_none()
        
        entry_data.append({
            "id": entry.id,
            "timesheet_id": entry.timesheet_id,
            "docket_number": timesheet.docket_number if timesheet else None,
            "worker_name": f"{worker.first_name} {worker.surname}" if worker else "Unknown",
            "worker_email": worker.email if worker else None,
            "day_of_week": entry.day_of_week,
            "entry_date": entry.entry_date.isoformat(),
            "clock_in_time": entry.clock_in_time.isoformat() if entry.clock_in_time else None,
            "clock_out_time": entry.clock_out_time.isoformat() if entry.clock_out_time else None,
            "total_hours": entry.total_hours,
            "worked_as": entry.worked_as,
            "clock_in_address": entry.clock_in_address,
            "host_company_name": entry.host_company_name,
            "supervisor_name": entry.supervisor_name,
            "supervisor_contact": entry.supervisor_contact,
            "supervisor_signature": entry.supervisor_signature,
            "submitted_at": entry.submitted_at.isoformat() if entry.submitted_at else None,
        })
    
    return {"entries": entry_data}
