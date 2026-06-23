"""
RAW Labour Hire - Timesheets API
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from datetime import datetime, date, timedelta
from typing import Optional, List
import asyncio
import pytz
import re

from ..database import get_db

# Australian Eastern Time (Melbourne)
MELBOURNE_TZ = pytz.timezone('Australia/Melbourne')

def get_melbourne_now():
    """Get current time in Melbourne, Australia (AEST/AEDT)"""
    return datetime.now(MELBOURNE_TZ)
from ..models import User, Timesheet, TimesheetEntry, TimesheetStatus, InjuryStatus, Client, JobSite
from ..services.timesheet_helpers import (
    summarize_entries,
    sync_timesheet_status,
    matches_admin_status_filter,
)
from .auth import get_current_user, resolve_user_id

router = APIRouter()


# ==================== ADMIN DASHBOARD ENDPOINTS ====================

@router.get("/admin/all")
async def get_all_timesheets_admin(
    status: Optional[str] = None,
    worker_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get all active (non-archived) timesheets for admin dashboard"""
    query = select(Timesheet).where(Timesheet.archived_at.is_(None)).order_by(Timesheet.week_starting.desc())
    if worker_id:
        query = query.where(Timesheet.worker_id == worker_id)

    result = await db.execute(query)
    timesheets = result.scalars().all()

    response_data = []
    for ts in timesheets:
        worker_result = await db.execute(select(User).where(User.id == ts.worker_id))
        worker = worker_result.scalar_one_or_none()

        client_result = await db.execute(select(Client).where(Client.id == ts.client_id))
        client = client_result.scalar_one_or_none()

        job_site_name = None
        if ts.job_site_id:
            site_result = await db.execute(select(JobSite).where(JobSite.id == ts.job_site_id))
            site = site_result.scalar_one_or_none()
            job_site_name = site.name if site else None

        entries_result = await db.execute(
            select(TimesheetEntry)
            .where(TimesheetEntry.timesheet_id == ts.id)
            .order_by(TimesheetEntry.entry_date)
        )
        entries = entries_result.scalars().all()
        summary = summarize_entries(entries)

        if not matches_admin_status_filter(summary["display_status"], status):
            continue

        response_data.append({
            "id": ts.id,
            "docket_number": ts.docket_number,
            "worker_id": ts.worker_id,
            "worker_name": f"{worker.first_name} {worker.surname}" if worker else "Unknown",
            "client_id": ts.client_id,
            "client_name": client.name if client else None,
            "job_site_id": ts.job_site_id,
            "job_site_name": job_site_name,
            "week_starting": ts.week_starting.isoformat(),
            "week_ending": ts.week_ending.isoformat(),
            "status": ts.status.value,
            "display_status": summary["display_status"],
            "entries_summary": summary["entries_summary"],
            "total_ordinary_hours": ts.total_ordinary_hours or 0,
            "total_overtime_hours": ts.total_overtime_hours or 0,
            "total_hours": ts.total_hours or 0,
            "approved_hours": summary["approved_hours"],
            "supervisor_name": ts.supervisor_name,
            "supervisor_contact": ts.supervisor_contact,
            "supervisor_signature": ts.supervisor_signature,
            "submitted_at": ts.submitted_at.isoformat() if ts.submitted_at else None,
            "submitted_entries_count": summary["submitted_entries_count"],
            "approved_entries_count": summary["approved_entries_count"],
            "total_entries_count": summary["total_entries_count"],
            "entries": [
                {
                    "entry_date": e.entry_date.isoformat(),
                    "day_of_week": e.day_of_week,
                    "entry_status": e.entry_status or "draft",
                    "clock_in": e.clock_in_time is not None,
                    "clock_out": e.clock_out_time is not None,
                    "total_hours": e.total_hours or 0,
                }
                for e in entries
            ],
        })

    return {"timesheets": response_data}


@router.get("/admin/archived")
async def get_archived_timesheets(
    db: AsyncSession = Depends(get_db)
):
    """Get all archived timesheets for admin dashboard"""
    query = select(Timesheet).where(Timesheet.archived_at.isnot(None)).order_by(Timesheet.archived_at.desc())
    
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
            "archived_at": ts.archived_at.isoformat() if ts.archived_at else None,
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


class SubmitOnBehalfRequest(BaseModel):
    supervisor_name: Optional[str] = None
    supervisor_contact: Optional[str] = None
    host_company_name: Optional[str] = None


@router.post("/admin/{timesheet_id}/submit-on-behalf")
async def admin_submit_on_behalf(
    timesheet_id: int,
    request: SubmitOnBehalfRequest = None,
    db: AsyncSession = Depends(get_db)
):
    """Admin submits a clocked-but-unsent docket on the worker's behalf.

    Used when a worker clocked out but never completed the supervisor-signature
    step, leaving the docket as a draft that never reached Pending Approval. This
    marks all un-submitted day-entries as submitted (recording that admin did it)
    and moves the docket into Pending Approval so it can be approved normally.
    """
    result = await db.execute(select(Timesheet).where(Timesheet.id == timesheet_id))
    timesheet = result.scalar_one_or_none()
    if not timesheet:
        raise HTTPException(status_code=404, detail="Timesheet not found")

    entries_result = await db.execute(
        select(TimesheetEntry).where(TimesheetEntry.timesheet_id == timesheet_id)
    )
    entries = entries_result.scalars().all()

    req = request or SubmitOnBehalfRequest()
    submitted_count = 0
    for entry in entries:
        if entry.entry_status in ("submitted", "approved"):
            continue
        entry.entry_status = "submitted"
        entry.submitted_at = datetime.utcnow()
        if req.host_company_name:
            entry.host_company_name = req.host_company_name
        entry.supervisor_name = req.supervisor_name or "Submitted by admin"
        if req.supervisor_contact:
            entry.supervisor_contact = req.supervisor_contact
        submitted_count += 1

    if submitted_count == 0:
        raise HTTPException(status_code=400, detail="No un-submitted entries on this docket")

    sync_timesheet_status(timesheet, entries)
    if not timesheet.submitted_at:
        timesheet.submitted_at = datetime.utcnow()

    await db.commit()

    return {
        "message": "Timesheet submitted on behalf of worker",
        "docket_number": timesheet.docket_number,
        "status": timesheet.status.value,
        "entries_submitted": submitted_count,
    }


@router.delete("/{timesheet_id}")
async def archive_timesheet(
    timesheet_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Archive a timesheet (soft delete) - moves to archived folder"""
    result = await db.execute(select(Timesheet).where(Timesheet.id == timesheet_id))
    timesheet = result.scalar_one_or_none()
    
    if not timesheet:
        raise HTTPException(status_code=404, detail="Timesheet not found")
    
    # Soft delete - set archived_at timestamp
    timesheet.archived_at = datetime.utcnow()
    await db.commit()
    
    return {"message": "Timesheet archived", "id": timesheet_id}


@router.post("/{timesheet_id}/restore")
async def restore_timesheet(
    timesheet_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Restore an archived timesheet back to active"""
    result = await db.execute(select(Timesheet).where(Timesheet.id == timesheet_id))
    timesheet = result.scalar_one_or_none()
    
    if not timesheet:
        raise HTTPException(status_code=404, detail="Timesheet not found")
    
    if not timesheet.archived_at:
        raise HTTPException(status_code=400, detail="Timesheet is not archived")
    
    # Restore by clearing archived_at
    timesheet.archived_at = None
    await db.commit()
    
    return {"message": "Timesheet restored", "id": timesheet_id}


def get_pay_week_range(reference_date: Optional[date] = None) -> tuple[date, date]:
    """
    RAW pay week: Saturday → Friday.
    Returns (week_start, week_end) for the pay week containing reference_date.
    If reference_date is None, uses today (Melbourne local).
    """
    if reference_date is None:
        reference_date = get_melbourne_now().date()
    # weekday(): Mon=0 ... Fri=4 ... Sat=5 ... Sun=6
    # Days since most recent Saturday: Sat=0, Sun=1, Mon=2, Tue=3, Wed=4, Thu=5, Fri=6
    days_since_saturday = (reference_date.weekday() - 5) % 7
    week_start = reference_date - timedelta(days=days_since_saturday)  # Saturday
    week_end = week_start + timedelta(days=6)                          # Friday
    return week_start, week_end


@router.post("/admin/archive-all-active")
async def archive_all_active_timesheets(
    db: AsyncSession = Depends(get_db)
):
    """
    One-time cleanup: soft-archive every currently active (non-archived) timesheet.
    Used to clear the slate before re-launch. Recoverable via the Archived tab.
    """
    result = await db.execute(
        select(Timesheet).where(Timesheet.archived_at.is_(None))
    )
    timesheets = result.scalars().all()

    now = datetime.utcnow()
    archived_ids = []
    for ts in timesheets:
        ts.archived_at = now
        archived_ids.append(ts.id)

    await db.commit()
    return {
        "message": f"Archived {len(archived_ids)} active timesheets",
        "archived_count": len(archived_ids),
        "archived_ids": archived_ids,
    }


@router.post("/admin/archive-prior-week")
async def archive_prior_pay_week(
    db: AsyncSession = Depends(get_db)
):
    """
    Archive APPROVED timesheets from the prior RAW pay week (Saturday → Friday).
    Drafts and pending stay visible (still need action).
    Rejected timesheets older than 14 days also get archived.
    Called manually via dashboard button OR weekly by the scheduler.
    """
    today = get_melbourne_now().date()
    current_week_start, _ = get_pay_week_range(today)
    prior_week_start = current_week_start - timedelta(days=7)
    prior_week_end = current_week_start - timedelta(days=1)

    archived_ids = []
    now = datetime.utcnow()

    # Approved timesheets overlapping the prior pay week
    approved_q = select(Timesheet).where(
        Timesheet.archived_at.is_(None),
        Timesheet.status == TimesheetStatus.APPROVED,
        Timesheet.week_ending >= prior_week_start,
        Timesheet.week_starting <= prior_week_end,
    )
    approved = (await db.execute(approved_q)).scalars().all()
    for ts in approved:
        ts.archived_at = now
        archived_ids.append(ts.id)

    # Rejected timesheets older than 14 days
    cutoff = today - timedelta(days=14)
    rejected_q = select(Timesheet).where(
        Timesheet.archived_at.is_(None),
        Timesheet.status == TimesheetStatus.REJECTED,
        Timesheet.week_ending < cutoff,
    )
    rejected = (await db.execute(rejected_q)).scalars().all()
    for ts in rejected:
        ts.archived_at = now
        archived_ids.append(ts.id)

    await db.commit()
    return {
        "message": f"Archived {len(archived_ids)} timesheets from pay week {prior_week_start} → {prior_week_end}",
        "prior_week_start": prior_week_start.isoformat(),
        "prior_week_end": prior_week_end.isoformat(),
        "archived_count": len(archived_ids),
        "approved_archived": len(approved),
        "rejected_archived": len(rejected),
    }


@router.delete("/{timesheet_id}/permanent")
async def permanently_delete_timesheet(
    timesheet_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Permanently delete a timesheet and all its entries (cannot be undone)"""
    result = await db.execute(select(Timesheet).where(Timesheet.id == timesheet_id))
    timesheet = result.scalar_one_or_none()
    
    if not timesheet:
        raise HTTPException(status_code=404, detail="Timesheet not found")
    
    # Delete all entries first
    await db.execute(
        TimesheetEntry.__table__.delete().where(TimesheetEntry.timesheet_id == timesheet_id)
    )
    
    # Delete the timesheet
    await db.delete(timesheet)
    await db.commit()
    
    return {"message": "Timesheet permanently deleted"}


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
    # Use Australian Eastern Time
    today = get_melbourne_now().date()
    # Get the start (Saturday) of the current RAW pay week (Sat -> Fri)
    week_start = today - timedelta(days=(today.weekday() - 5) % 7)
    
    result = await db.execute(
        select(Timesheet)
        .where(
            Timesheet.worker_id == current_user.id,
            Timesheet.week_starting == week_start
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
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific timesheet with all entries."""
    result = await db.execute(
        select(Timesheet).where(Timesheet.id == timesheet_id)
    )
    timesheet = result.scalar_one_or_none()
    
    if not timesheet:
        raise HTTPException(status_code=404, detail="Timesheet not found")

    # Ownership: a non-admin worker may only view their own timesheet.
    if not getattr(request.state, "is_admin", False):
        if str(timesheet.worker_id) != str(getattr(request.state, "token_sub", "")):
            raise HTTPException(status_code=403, detail="Access denied")
    
    # Get worker info
    worker_result = await db.execute(select(User).where(User.id == timesheet.worker_id))
    worker = worker_result.scalar_one_or_none()
    worker_name = f"{worker.first_name} {worker.surname}" if worker else "Unknown"
    
    # Get client info from timesheet client
    client_name = None
    if timesheet.client_id:
        client_result = await db.execute(select(Client).where(Client.id == timesheet.client_id))
        client = client_result.scalar_one_or_none()
        client_name = client.name if client else None
    
    # Get entries with job site names
    result = await db.execute(
        select(TimesheetEntry)
        .where(TimesheetEntry.timesheet_id == timesheet_id)
        .order_by(TimesheetEntry.entry_date)
    )
    entries = result.scalars().all()
    
    # Build entries with job site names
    entries_data = []
    for e in entries:
        # Get job site name if job_site_id exists
        job_site_name = None
        job_site_address = None
        if e.job_site_id:
            job_site_result = await db.execute(select(JobSite).where(JobSite.id == e.job_site_id))
            job_site = job_site_result.scalar_one_or_none()
            job_site_name = job_site.name if job_site else None
            job_site_address = job_site.address if job_site else None
        
        entries_data.append({
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
            "gross_hours": e.gross_hours,  # Hours before break deduction
            "unpaid_break_minutes": e.unpaid_break_minutes if e.unpaid_break_minutes is not None else 30,
            "paid_break_minutes": e.paid_break_minutes or 0,
            "worked_as": e.worked_as,
            "comments": e.comments,
            "first_aid_injury": e.first_aid_injury,
            # GPS coordinates
            "clock_in_address": e.clock_in_address,
            "clock_in_latitude": e.clock_in_latitude,
            "clock_in_longitude": e.clock_in_longitude,
            "clock_out_address": e.clock_out_address,
            "clock_out_latitude": e.clock_out_latitude,
            "clock_out_longitude": e.clock_out_longitude,
            # Status and supervisor
            "entry_status": e.entry_status or "draft",
            "job_site_name": job_site_name,
            "job_site_address": job_site_address,
            "company_name": e.host_company_name,
            "host_company_name": e.host_company_name,
            "supervisor_name": e.supervisor_name,
            "supervisor_contact": e.supervisor_contact,
            "supervisor_signature": e.supervisor_signature
        })
    
    summary = summarize_entries(entries)
    return {
        "id": timesheet.id,
        "docket_number": timesheet.docket_number,
        "order_number": timesheet.order_number,
        "week_starting": timesheet.week_starting.isoformat(),
        "week_ending": timesheet.week_ending.isoformat(),
        "status": timesheet.status.value,
        "display_status": summary["display_status"],
        "entries_summary": summary["entries_summary"],
        "approved_entries_count": summary["approved_entries_count"],
        "submitted_entries_count": summary["submitted_entries_count"],
        "total_entries_count": summary["total_entries_count"],
        "worker_name": worker_name,
        "client_name": client_name,
        "total_ordinary_hours": timesheet.total_ordinary_hours,
        "total_overtime_hours": timesheet.total_overtime_hours,
        "total_hours": timesheet.total_hours,
        "injury_reported": timesheet.injury_reported.value if timesheet.injury_reported else "n/a",
        "supervisor_signed_at": timesheet.supervisor_signed_at.isoformat() if timesheet.supervisor_signed_at else None,
        "supervisor_name": timesheet.supervisor_name,
        "supervisor_contact": timesheet.supervisor_contact,
        "supervisor_signature": timesheet.supervisor_signature,
        "entries": entries_data
    }


@router.post("/{timesheet_id}/submit")
async def submit_timesheet(
    timesheet_id: int,
    request: SubmitTimesheetRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Submit a timesheet for supervisor approval."""
    result = await db.execute(
        select(Timesheet).where(Timesheet.id == timesheet_id)
    )
    timesheet = result.scalar_one_or_none()
    
    if not timesheet:
        raise HTTPException(status_code=404, detail="Timesheet not found")

    # Ownership: a non-admin worker may only submit their own timesheet.
    if not getattr(http_request.state, "is_admin", False):
        if str(timesheet.worker_id) != str(getattr(http_request.state, "token_sub", "")):
            raise HTTPException(status_code=403, detail="Access denied")
    
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
    try:
        timesheet.injury_reported = InjuryStatus(request.injury_reported)
    except ValueError:
        timesheet.injury_reported = InjuryStatus.NA
    
    await db.commit()
    
    # Send email notification in the background so a slow/down mail server never
    # delays or blocks the worker's submission.
    _fire_and_forget(send_timesheet_notification(
        worker_name=worker_name,
        docket_number=timesheet.docket_number,
        company_name=request.company_name,
        supervisor_name=request.supervisor_name,
        supervisor_contact=request.supervisor_contact,
        week_starting=timesheet.week_starting.isoformat(),
        week_ending=timesheet.week_ending.isoformat(),
        total_hours=timesheet.total_hours,
    ))
    
    return {
        "message": "Timesheet submitted for approval",
        "docket_number": timesheet.docket_number,
        "status": timesheet.status.value
    }


@router.post("/entries/{entry_id}/submit")
async def submit_entry(
    entry_id: int,
    request: SubmitEntryRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Submit an individual daily entry for approval"""
    result = await db.execute(
        select(TimesheetEntry).where(TimesheetEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    
    # Ownership: a worker may only submit entries on their own timesheet.
    if not getattr(http_request.state, "is_admin", False):
        owner_result = await db.execute(
            select(Timesheet.worker_id).where(Timesheet.id == entry.timesheet_id)
        )
        owner_id = owner_result.scalar_one_or_none()
        token_sub = getattr(http_request.state, "token_sub", None)
        if owner_id is None or str(owner_id) != str(token_sub):
            raise HTTPException(status_code=403, detail="You can only submit your own timesheet")
    
    if entry.entry_status == "submitted":
        raise HTTPException(status_code=400, detail="Entry already submitted")
    
    # Reject anything that isn't a genuine base64 image data URL, so a malicious
    # signature value can never become an XSS sink in the admin dashboard.
    sig = request.supervisor_signature
    if sig and not re.match(r"^data:image/(png|jpe?g|gif|webp);base64,[A-Za-z0-9+/=\s]+$", sig):
        raise HTTPException(status_code=400, detail="Invalid signature format")
    
    # Update entry with submission details
    entry.entry_status = "submitted"
    entry.host_company_name = request.company_name
    entry.supervisor_name = request.supervisor_name
    entry.supervisor_contact = request.supervisor_contact
    entry.supervisor_signature = request.supervisor_signature
    entry.submitted_at = datetime.utcnow()

    timesheet_result = await db.execute(
        select(Timesheet).where(Timesheet.id == entry.timesheet_id)
    )
    timesheet = timesheet_result.scalar_one_or_none()
    if timesheet:
        all_entries_result = await db.execute(
            select(TimesheetEntry).where(TimesheetEntry.timesheet_id == timesheet.id)
        )
        sync_timesheet_status(timesheet, all_entries_result.scalars().all())

    await db.commit()

    # Get timesheet and worker info for notification
    if not timesheet:
        timesheet_result = await db.execute(
            select(Timesheet).where(Timesheet.id == entry.timesheet_id)
        )
        timesheet = timesheet_result.scalar_one_or_none()
    
    worker_result = await db.execute(
        select(User).where(User.id == timesheet.worker_id)
    )
    worker = worker_result.scalar_one_or_none()
    worker_name = f"{worker.first_name} {worker.surname}" if worker else "Unknown"
    
    # Send email notification in the background so a slow/down mail server never
    # delays or blocks the worker's submission.
    _fire_and_forget(send_entry_notification(
        worker_name=worker_name,
        docket_number=timesheet.docket_number if timesheet else "N/A",
        company_name=request.company_name,
        supervisor_name=request.supervisor_name,
        supervisor_contact=request.supervisor_contact,
        entry_date=entry.entry_date.isoformat(),
        total_hours=entry.total_hours or 0,
    ))
    
    return {
        "message": "Entry submitted for approval",
        "entry_id": entry.id,
        "entry_date": entry.entry_date.isoformat(),
        "docket_number": timesheet.docket_number if timesheet else None,
        "status": entry.entry_status
    }


_bg_tasks: set = set()


async def _notify_safely(coro):
    """Run a notification coroutine, swallowing all errors so email problems can
    never affect (or delay) the worker's request."""
    try:
        await coro
    except Exception as e:
        print(f"Notification failed: {e}")


def _fire_and_forget(coro):
    """Schedule a notification in the background and return immediately."""
    task = asyncio.create_task(_notify_safely(coro))
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


def _smtp_send_blocking(smtp_host, smtp_port, smtp_user, smtp_password, notification_email, msg):
    """Blocking SMTP send. MUST be run in a worker thread (asyncio.to_thread) so it
    never blocks the event loop, and uses a socket timeout so a stalled mail server
    can never freeze the whole backend."""
    import smtplib
    with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_user, notification_email, msg.as_string())


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
    
    # Run the blocking SMTP work in a thread with a hard timeout so a slow/stalled
    # mail server can never block the event loop (which would hang the whole API).
    await asyncio.wait_for(
        asyncio.to_thread(
            _smtp_send_blocking,
            smtp_host, smtp_port, smtp_user, smtp_password, notification_email, msg,
        ),
        timeout=20,
    )


async def send_entry_notification(
    worker_name: str,
    docket_number: str,
    company_name: str,
    supervisor_name: str,
    supervisor_contact: str,
    entry_date: str,
    total_hours: float,
):
    """Send email notification when daily entry is submitted"""
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
    
    subject = f"Timesheet Entry Submitted - {worker_name} - #{docket_number} - {entry_date}"
    
    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <h2 style="color: #1E3A8A;">Daily Timesheet Entry Submitted</h2>
        <p>A worker has clocked out and submitted their daily timesheet entry for approval.</p>
        
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
                <td style="padding: 8px; border-bottom: 1px solid #ddd; font-weight: bold;">Date:</td>
                <td style="padding: 8px; border-bottom: 1px solid #ddd;">{entry_date}</td>
            </tr>
            <tr>
                <td style="padding: 8px; border-bottom: 1px solid #ddd; font-weight: bold;">Hours Worked:</td>
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
                <td style="padding: 8px; border-bottom: 1px solid #ddd; font-weight: bold;">Supervisor Phone:</td>
                <td style="padding: 8px; border-bottom: 1px solid #ddd;">{supervisor_contact}</td>
            </tr>
        </table>
        
        <p style="margin-top: 20px;">
            <a href="https://admin.rawlabourhire.com/admin/" 
               style="background-color: #1E3A8A; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">
                Review in Admin Dashboard
            </a>
        </p>
        
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
    
    # Run the blocking SMTP work in a thread with a hard timeout so a slow/stalled
    # mail server can never block the event loop (which would hang the whole API).
    await asyncio.wait_for(
        asyncio.to_thread(
            _smtp_send_blocking,
            smtp_host, smtp_port, smtp_user, smtp_password, notification_email, msg,
        ),
        timeout=20,
    )


@router.get("/")
async def list_timesheets(
    http_request: Request,
    status: Optional[str] = None,
    limit: int = 20,
    user_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    """List timesheets for the current user."""
    from sqlalchemy import func
    
    uid = resolve_user_id(http_request, user_id)
    if uid is None:
        return {"timesheets": []}
    result = await db.execute(select(User).where(User.id == uid))
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
            (Timesheet.status == TimesheetStatus.SUBMITTED) | (Timesheet.id.in_(subquery))
        )
    elif status == 'approved':
        # Get timesheets that are approved OR have approved entries
        subquery = select(TimesheetEntry.timesheet_id).where(
            TimesheetEntry.entry_status == 'approved'
        ).distinct()
        query = select(Timesheet).where(
            Timesheet.worker_id == current_user.id,
            (Timesheet.status == TimesheetStatus.APPROVED) | (Timesheet.id.in_(subquery))
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
    """Approve a submitted entry and update parent timesheet if all entries approved"""
    result = await db.execute(
        select(TimesheetEntry).where(TimesheetEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    
    entry.entry_status = "approved"

    all_entries_result = await db.execute(
        select(TimesheetEntry).where(TimesheetEntry.timesheet_id == entry.timesheet_id)
    )
    all_entries = all_entries_result.scalars().all()

    ts_result = await db.execute(select(Timesheet).where(Timesheet.id == entry.timesheet_id))
    timesheet = ts_result.scalar_one_or_none()

    if timesheet:
        sync_timesheet_status(timesheet, all_entries)

    await db.commit()

    summary = summarize_entries(all_entries)
    return {
        "message": "Entry approved",
        "entry_id": entry_id,
        "timesheet_status": timesheet.status.value if timesheet else None,
        "display_status": summary["display_status"],
    }


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

    all_entries_result = await db.execute(
        select(TimesheetEntry).where(TimesheetEntry.timesheet_id == entry.timesheet_id)
    )
    all_entries = all_entries_result.scalars().all()
    ts_result = await db.execute(select(Timesheet).where(Timesheet.id == entry.timesheet_id))
    timesheet = ts_result.scalar_one_or_none()
    if timesheet:
        sync_timesheet_status(timesheet, all_entries)

    await db.commit()

    return {"message": "Entry rejected", "entry_id": entry_id}


@router.delete("/admin/entries/{entry_id}")
async def delete_entry(
    entry_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Delete a specific timesheet entry (admin) - useful for fixing bad data"""
    result = await db.execute(
        select(TimesheetEntry).where(TimesheetEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    
    timesheet_id = entry.timesheet_id
    
    # Delete the entry
    await db.delete(entry)
    await db.commit()
    
    # Recalculate timesheet totals
    ts_result = await db.execute(select(Timesheet).where(Timesheet.id == timesheet_id))
    timesheet = ts_result.scalar_one_or_none()
    
    if timesheet:
        entries_result = await db.execute(
            select(TimesheetEntry).where(TimesheetEntry.timesheet_id == timesheet_id)
        )
        entries = entries_result.scalars().all()
        
        timesheet.total_ordinary_hours = sum(e.ordinary_hours or 0 for e in entries)
        timesheet.total_overtime_hours = sum(e.overtime_hours or 0 for e in entries)
        timesheet.total_hours = timesheet.total_ordinary_hours + timesheet.total_overtime_hours
        sync_timesheet_status(timesheet, entries)
        await db.commit()
    
    return {"message": "Entry deleted", "entry_id": entry_id}


class EditEntryRequest(BaseModel):
    clock_in_time: Optional[str] = None  # ISO format datetime string
    clock_out_time: Optional[str] = None  # ISO format datetime string
    entry_date: Optional[str] = None  # YYYY-MM-DD format
    clock_in_address: Optional[str] = None
    clock_out_address: Optional[str] = None
    comments: Optional[str] = None
    unpaid_break_minutes: Optional[int] = None  # Unpaid break (deducted from hours)
    paid_break_minutes: Optional[int] = None  # Paid break (tracked but not deducted)


@router.put("/admin/entries/{entry_id}")
async def edit_entry(
    entry_id: int,
    request: EditEntryRequest,
    db: AsyncSession = Depends(get_db)
):
    """Edit a timesheet entry (admin) - for correcting clock times"""
    result = await db.execute(
        select(TimesheetEntry).where(TimesheetEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    
    # Update fields if provided
    if request.clock_in_time:
        entry.clock_in_time = datetime.fromisoformat(request.clock_in_time.replace('Z', '+00:00').replace('+00:00', ''))
        entry.time_start = entry.clock_in_time.time()
    
    if request.clock_out_time:
        entry.clock_out_time = datetime.fromisoformat(request.clock_out_time.replace('Z', '+00:00').replace('+00:00', ''))
        entry.time_finish = entry.clock_out_time.time()
    
    if request.entry_date:
        entry.entry_date = date.fromisoformat(request.entry_date)
    
    if request.clock_in_address is not None:
        entry.clock_in_address = request.clock_in_address
    
    if request.clock_out_address is not None:
        entry.clock_out_address = request.clock_out_address
    
    if request.comments is not None:
        entry.comments = request.comments
    
    if request.unpaid_break_minutes is not None:
        entry.unpaid_break_minutes = request.unpaid_break_minutes
    
    if request.paid_break_minutes is not None:
        entry.paid_break_minutes = request.paid_break_minutes
    
    # Recalculate hours if both clock times are set
    if entry.clock_in_time and entry.clock_out_time:
        total_seconds = (entry.clock_out_time - entry.clock_in_time).total_seconds()
        gross_hours = total_seconds / 3600
        
        # Deduct unpaid break
        unpaid_break = entry.unpaid_break_minutes if entry.unpaid_break_minutes is not None else 30
        break_hours = unpaid_break / 60
        net_hours = max(0, gross_hours - break_hours)
        
        entry.gross_hours = round(gross_hours, 2)
        
        # Cap ordinary hours at 8, rest is overtime (based on NET hours after break)
        entry.ordinary_hours = min(8.0, net_hours)
        entry.overtime_hours = max(0, net_hours - 8.0)
        entry.total_hours = round(net_hours, 2)  # Total PAID hours (after break deduction)
    
    await db.commit()
    
    # Recalculate timesheet totals
    ts_result = await db.execute(select(Timesheet).where(Timesheet.id == entry.timesheet_id))
    timesheet = ts_result.scalar_one_or_none()
    
    if timesheet:
        entries_result = await db.execute(
            select(TimesheetEntry).where(TimesheetEntry.timesheet_id == entry.timesheet_id)
        )
        entries = entries_result.scalars().all()
        
        timesheet.total_ordinary_hours = sum(e.ordinary_hours or 0 for e in entries)
        timesheet.total_overtime_hours = sum(e.overtime_hours or 0 for e in entries)
        timesheet.total_hours = timesheet.total_ordinary_hours + timesheet.total_overtime_hours
        await db.commit()
    
    return {
        "message": "Entry updated",
        "entry_id": entry_id,
        "clock_in_time": entry.clock_in_time.isoformat() if entry.clock_in_time else None,
        "clock_out_time": entry.clock_out_time.isoformat() if entry.clock_out_time else None,
        "gross_hours": entry.gross_hours,
        "total_hours": entry.total_hours,  # Net hours after break
        "ordinary_hours": entry.ordinary_hours,
        "overtime_hours": entry.overtime_hours,
        "unpaid_break_minutes": entry.unpaid_break_minutes,
        "paid_break_minutes": entry.paid_break_minutes
    }


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
