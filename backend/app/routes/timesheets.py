"""
RAW Labour Hire - Timesheets API
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from datetime import datetime, date
from typing import Optional, List

from ..database import get_db
from ..models import User, Timesheet, TimesheetEntry, TimesheetStatus, InjuryStatus
from .auth import get_current_user

router = APIRouter()


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
    supervisor_name: str
    supervisor_contact: str
    injury_reported: str = "n/a"  # yes, no, n/a


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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific timesheet with all entries"""
    result = await db.execute(
        select(Timesheet).where(Timesheet.id == timesheet_id)
    )
    timesheet = result.scalar_one_or_none()
    
    if not timesheet:
        raise HTTPException(status_code=404, detail="Timesheet not found")
    
    # Check permission (worker can see their own, supervisors/admins can see all)
    if timesheet.worker_id != current_user.id and current_user.role.value == "worker":
        raise HTTPException(status_code=403, detail="Access denied")
    
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
                "ordinary_hours": e.ordinary_hours,
                "overtime_hours": e.overtime_hours,
                "total_hours": e.total_hours,
                "worked_as": e.worked_as,
                "comments": e.comments,
                "first_aid_injury": e.first_aid_injury,
                "clock_in_address": e.clock_in_address,
                "clock_out_address": e.clock_out_address
            }
            for e in entries
        ]
    }


@router.post("/{timesheet_id}/submit")
async def submit_timesheet(
    timesheet_id: int,
    request: SubmitTimesheetRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Submit a timesheet for supervisor approval"""
    result = await db.execute(
        select(Timesheet).where(Timesheet.id == timesheet_id)
    )
    timesheet = result.scalar_one_or_none()
    
    if not timesheet:
        raise HTTPException(status_code=404, detail="Timesheet not found")
    
    if timesheet.worker_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if timesheet.status != TimesheetStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Timesheet already submitted")
    
    # Update timesheet
    timesheet.status = TimesheetStatus.SUBMITTED
    timesheet.submitted_at = datetime.utcnow()
    timesheet.supervisor_contact = request.supervisor_contact
    timesheet.injury_reported = InjuryStatus(request.injury_reported)
    
    await db.commit()
    
    return {
        "message": "Timesheet submitted for approval",
        "docket_number": timesheet.docket_number,
        "status": timesheet.status.value
    }


@router.get("/")
async def list_timesheets(
    status: Optional[str] = None,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List timesheets for the current user"""
    query = select(Timesheet).where(Timesheet.worker_id == current_user.id)
    
    if status:
        query = query.where(Timesheet.status == TimesheetStatus(status))
    
    query = query.order_by(Timesheet.week_starting.desc()).limit(limit)
    
    result = await db.execute(query)
    timesheets = result.scalars().all()
    
    return {
        "timesheets": [
            {
                "id": ts.id,
                "docket_number": ts.docket_number,
                "week_starting": ts.week_starting.isoformat(),
                "week_ending": ts.week_ending.isoformat(),
                "status": ts.status.value,
                "total_hours": ts.total_hours,
                "submitted_at": ts.submitted_at.isoformat() if ts.submitted_at else None
            }
            for ts in timesheets
        ]
    }


# Import timedelta for the get_current_timesheet function
from datetime import timedelta
