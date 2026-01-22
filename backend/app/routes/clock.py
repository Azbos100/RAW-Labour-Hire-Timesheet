"""
RAW Labour Hire - Clock In/Out API
GPS-enabled time tracking
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from datetime import datetime, date, timedelta
from typing import Optional
from geopy.geocoders import Nominatim
from geopy.distance import geodesic

from ..database import get_db
from ..models import User, TimesheetEntry, Timesheet, JobSite, TimesheetStatus
from ..auth import get_current_user

router = APIRouter()

# Geocoder for reverse geocoding GPS coordinates to addresses
geolocator = Nominatim(user_agent="raw-labour-hire")


class ClockInRequest(BaseModel):
    """Request to clock in at a job"""
    latitude: float
    longitude: float
    job_site_id: Optional[int] = None
    worked_as: Optional[str] = None  # Job role


class ClockOutRequest(BaseModel):
    """Request to clock out from a job"""
    latitude: float
    longitude: float
    comments: Optional[str] = None
    first_aid_injury: bool = False


class ClockStatusResponse(BaseModel):
    """Current clock status"""
    is_clocked_in: bool
    clock_in_time: Optional[datetime] = None
    clock_in_address: Optional[str] = None
    current_entry_id: Optional[int] = None
    hours_worked_today: float = 0


def get_address_from_coords(lat: float, lon: float) -> str:
    """Reverse geocode coordinates to address"""
    try:
        location = geolocator.reverse(f"{lat}, {lon}", timeout=10)
        return location.address if location else f"{lat}, {lon}"
    except Exception:
        return f"{lat}, {lon}"


def calculate_hours(start: datetime, end: datetime) -> tuple[float, float]:
    """
    Calculate ordinary and overtime hours.
    Ordinary: first 8 hours
    Overtime: anything over 8 hours
    """
    total_seconds = (end - start).total_seconds()
    total_hours = total_seconds / 3600
    
    ordinary = min(total_hours, 8.0)
    overtime = max(total_hours - 8.0, 0.0)
    
    return round(ordinary, 2), round(overtime, 2)


def get_day_of_week(d: date) -> str:
    """Get day abbreviation (MON, TUE, etc.)"""
    days = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN']
    return days[d.weekday()]


def get_week_dates(d: date) -> tuple[date, date]:
    """Get Monday and Sunday of the week containing date d"""
    monday = d - timedelta(days=d.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


@router.get("/status", response_model=ClockStatusResponse)
async def get_clock_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get current clock status for the user.
    Returns whether they're clocked in and current session details.
    """
    today = date.today()
    
    # Find today's entry that's clocked in but not clocked out
    result = await db.execute(
        select(TimesheetEntry)
        .join(Timesheet)
        .where(
            Timesheet.worker_id == current_user.id,
            TimesheetEntry.entry_date == today,
            TimesheetEntry.clock_in_time.isnot(None),
            TimesheetEntry.clock_out_time.is_(None)
        )
    )
    active_entry = result.scalar_one_or_none()
    
    if active_entry:
        # Calculate hours worked so far
        hours_so_far = (datetime.utcnow() - active_entry.clock_in_time).total_seconds() / 3600
        
        return ClockStatusResponse(
            is_clocked_in=True,
            clock_in_time=active_entry.clock_in_time,
            clock_in_address=active_entry.clock_in_address,
            current_entry_id=active_entry.id,
            hours_worked_today=round(hours_so_far, 2)
        )
    
    # Check total hours worked today (for completed entries)
    result = await db.execute(
        select(TimesheetEntry)
        .join(Timesheet)
        .where(
            Timesheet.worker_id == current_user.id,
            TimesheetEntry.entry_date == today,
            TimesheetEntry.clock_out_time.isnot(None)
        )
    )
    completed_entries = result.scalars().all()
    total_hours = sum(e.total_hours or 0 for e in completed_entries)
    
    return ClockStatusResponse(
        is_clocked_in=False,
        hours_worked_today=round(total_hours, 2)
    )


@router.post("/in")
async def clock_in(
    request: ClockInRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Clock in at a job site with GPS location.
    Creates or updates the timesheet entry for today.
    """
    now = datetime.utcnow()
    today = now.date()
    week_start, week_end = get_week_dates(today)
    
    # Check if already clocked in
    result = await db.execute(
        select(TimesheetEntry)
        .join(Timesheet)
        .where(
            Timesheet.worker_id == current_user.id,
            TimesheetEntry.entry_date == today,
            TimesheetEntry.clock_in_time.isnot(None),
            TimesheetEntry.clock_out_time.is_(None)
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Already clocked in. Please clock out first."
        )
    
    # Get or verify job site
    job_site = None
    client_id = None
    if request.job_site_id:
        result = await db.execute(
            select(JobSite).where(JobSite.id == request.job_site_id)
        )
        job_site = result.scalar_one_or_none()
        if job_site:
            client_id = job_site.client_id
            
            # Check if within geofence (optional warning)
            if job_site.latitude and job_site.longitude:
                distance = geodesic(
                    (request.latitude, request.longitude),
                    (job_site.latitude, job_site.longitude)
                ).meters
                if distance > job_site.geofence_radius:
                    # Log warning but allow clock in
                    pass  # TODO: Add warning to response
    
    if not client_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please select a valid job site/client"
        )
    
    # Get or create timesheet for this week
    result = await db.execute(
        select(Timesheet).where(
            Timesheet.worker_id == current_user.id,
            Timesheet.week_starting == week_start,
            Timesheet.client_id == client_id
        )
    )
    timesheet = result.scalar_one_or_none()
    
    if not timesheet:
        # Generate docket number
        result = await db.execute(select(Timesheet).order_by(Timesheet.id.desc()).limit(1))
        last_timesheet = result.scalar_one_or_none()
        last_docket = int(last_timesheet.docket_number) if last_timesheet else 12537
        new_docket = str(last_docket + 1)
        
        timesheet = Timesheet(
            docket_number=new_docket,
            worker_id=current_user.id,
            client_id=client_id,
            week_starting=week_start,
            week_ending=week_end,
            status=TimesheetStatus.DRAFT
        )
        db.add(timesheet)
        await db.flush()
    
    # Reverse geocode to get address
    clock_in_address = get_address_from_coords(request.latitude, request.longitude)
    
    # Create timesheet entry
    entry = TimesheetEntry(
        timesheet_id=timesheet.id,
        day_of_week=get_day_of_week(today),
        entry_date=today,
        job_site_id=request.job_site_id,
        time_start=now.time(),
        clock_in_time=now,
        clock_in_latitude=request.latitude,
        clock_in_longitude=request.longitude,
        clock_in_address=clock_in_address,
        worked_as=request.worked_as
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    
    return {
        "message": "Successfully clocked in",
        "entry_id": entry.id,
        "clock_in_time": now.isoformat(),
        "clock_in_address": clock_in_address,
        "docket_number": timesheet.docket_number,
        "job_site": job_site.name if job_site else None
    }


@router.post("/out")
async def clock_out(
    request: ClockOutRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Clock out from current job with GPS location.
    Calculates hours worked and updates timesheet.
    """
    now = datetime.utcnow()
    today = now.date()
    
    # Find active clock-in entry
    result = await db.execute(
        select(TimesheetEntry)
        .join(Timesheet)
        .where(
            Timesheet.worker_id == current_user.id,
            TimesheetEntry.entry_date == today,
            TimesheetEntry.clock_in_time.isnot(None),
            TimesheetEntry.clock_out_time.is_(None)
        )
    )
    entry = result.scalar_one_or_none()
    
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Not currently clocked in. Please clock in first."
        )
    
    # Reverse geocode clock out location
    clock_out_address = get_address_from_coords(request.latitude, request.longitude)
    
    # Calculate hours
    ordinary_hours, overtime_hours = calculate_hours(entry.clock_in_time, now)
    total_hours = ordinary_hours + overtime_hours
    
    # Update entry
    entry.time_finish = now.time()
    entry.clock_out_time = now
    entry.clock_out_latitude = request.latitude
    entry.clock_out_longitude = request.longitude
    entry.clock_out_address = clock_out_address
    entry.ordinary_hours = ordinary_hours
    entry.overtime_hours = overtime_hours
    entry.total_hours = total_hours
    entry.comments = request.comments
    entry.first_aid_injury = request.first_aid_injury
    
    # Update timesheet totals
    result = await db.execute(
        select(Timesheet).where(Timesheet.id == entry.timesheet_id)
    )
    timesheet = result.scalar_one()
    
    # Recalculate totals for entire timesheet
    result = await db.execute(
        select(TimesheetEntry).where(TimesheetEntry.timesheet_id == timesheet.id)
    )
    all_entries = result.scalars().all()
    
    timesheet.total_ordinary_hours = sum(e.ordinary_hours or 0 for e in all_entries)
    timesheet.total_overtime_hours = sum(e.overtime_hours or 0 for e in all_entries)
    timesheet.total_hours = timesheet.total_ordinary_hours + timesheet.total_overtime_hours
    
    await db.commit()
    
    return {
        "message": "Successfully clocked out",
        "entry_id": entry.id,
        "clock_in_time": entry.clock_in_time.isoformat(),
        "clock_out_time": now.isoformat(),
        "clock_out_address": clock_out_address,
        "ordinary_hours": ordinary_hours,
        "overtime_hours": overtime_hours,
        "total_hours": total_hours,
        "weekly_total": timesheet.total_hours
    }


@router.get("/history")
async def get_clock_history(
    days: int = 7,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get clock in/out history for the user.
    """
    start_date = date.today() - timedelta(days=days)
    
    result = await db.execute(
        select(TimesheetEntry)
        .join(Timesheet)
        .where(
            Timesheet.worker_id == current_user.id,
            TimesheetEntry.entry_date >= start_date
        )
        .order_by(TimesheetEntry.entry_date.desc())
    )
    entries = result.scalars().all()
    
    return {
        "entries": [
            {
                "id": e.id,
                "date": e.entry_date.isoformat(),
                "day": e.day_of_week,
                "clock_in_time": e.clock_in_time.isoformat() if e.clock_in_time else None,
                "clock_out_time": e.clock_out_time.isoformat() if e.clock_out_time else None,
                "clock_in_address": e.clock_in_address,
                "clock_out_address": e.clock_out_address,
                "ordinary_hours": e.ordinary_hours,
                "overtime_hours": e.overtime_hours,
                "total_hours": e.total_hours,
                "worked_as": e.worked_as,
                "comments": e.comments
            }
            for e in entries
        ],
        "total_entries": len(entries)
    }
