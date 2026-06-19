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
import pytz

from ..database import get_db

# Australian Eastern Time (Melbourne)
MELBOURNE_TZ = pytz.timezone('Australia/Melbourne')

def get_melbourne_now():
    """Get current time in Melbourne, Australia (AEST/AEDT)"""
    return datetime.now(MELBOURNE_TZ)
from ..models import User, TimesheetEntry, Timesheet, JobSite, TimesheetStatus
from .auth import get_current_user

router = APIRouter()

# Geocoder for reverse geocoding GPS coordinates to addresses
geolocator = Nominatim(user_agent="raw-labour-hire")


class ClockInRequest(BaseModel):
    """Request to clock in at a job"""
    latitude: float = 0  # Can be 0 if using manual address
    longitude: float = 0  # Can be 0 if using manual address
    address: Optional[str] = None  # Manual address override
    job_site_id: Optional[int] = None
    job_site_address: Optional[str] = None  # Manual job site address if no match detected
    worked_as: Optional[str] = None  # Job role
    user_id: Optional[int] = None  # Temporary until auth is fixed


class ClockOutRequest(BaseModel):
    """Request to clock out from a job"""
    latitude: float = 0  # Can be 0 if using manual address
    longitude: float = 0  # Can be 0 if using manual address
    address: Optional[str] = None  # Manual address override
    comments: Optional[str] = None
    first_aid_injury: bool = False
    user_id: Optional[int] = None  # Temporary until auth is fixed
    is_overtime: Optional[bool] = None  # True=working overtime, False=finished at assigned time, None=not specified


class ClockStatusResponse(BaseModel):
    """Current clock status"""
    is_clocked_in: bool
    clock_in_time: Optional[datetime] = None
    clock_in_address: Optional[str] = None
    current_entry_id: Optional[int] = None
    hours_worked_today: float = 0
    overtime_mode: bool = False  # When True, suppresses clock-out reminders
    # Weekly stats
    week_days_worked: int = 0
    week_total_hours: float = 0
    week_overtime_hours: float = 0


class OvertimeModeRequest(BaseModel):
    """Request to toggle overtime mode"""
    overtime_mode: bool
    user_id: Optional[int] = None


def get_address_from_coords(lat: float, lon: float) -> str:
    """Reverse geocode coordinates to address"""
    try:
        location = geolocator.reverse(f"{lat}, {lon}", timeout=10)
        return location.address if location else f"{lat}, {lon}"
    except Exception:
        return f"{lat}, {lon}"


def calculate_hours(start: datetime, end: datetime, unpaid_break_minutes: int = 30) -> tuple[float, float, float]:
    """
    Calculate gross hours, ordinary hours, and overtime hours.
    - Gross hours: total time between clock in and out
    - Net hours: gross hours minus unpaid break (only if shift >= 4 hours)
    - Ordinary: first 8 hours of net time
    - Overtime: anything over 8 hours of net time
    
    Returns: (ordinary_hours, overtime_hours, gross_hours)
    """
    total_seconds = (end - start).total_seconds()
    gross_hours = total_seconds / 3600
    
    # Only deduct unpaid break if shift is 4+ hours
    if gross_hours >= 4:
        break_hours = unpaid_break_minutes / 60
    else:
        break_hours = 0
    net_hours = max(0, gross_hours - break_hours)
    
    ordinary = min(net_hours, 8.0)
    overtime = max(net_hours - 8.0, 0.0)
    
    return round(ordinary, 2), round(overtime, 2), round(gross_hours, 2)


def get_day_of_week(d: date) -> str:
    """Get day abbreviation (MON, TUE, etc.)"""
    days = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN']
    return days[d.weekday()]


def get_week_dates(d: date) -> tuple[date, date]:
    """Get the RAW pay week (Saturday -> Friday) containing date d.

    weekday(): Mon=0 .. Fri=4 .. Sat=5 .. Sun=6
    Days since most recent Saturday: Sat=0, Sun=1, Mon=2 ... Fri=6
    """
    days_since_saturday = (d.weekday() - 5) % 7
    week_start = d - timedelta(days=days_since_saturday)  # Saturday
    week_end = week_start + timedelta(days=6)             # Friday
    return week_start, week_end


@router.get("/status", response_model=ClockStatusResponse)
async def get_clock_status(
    user_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Get current clock status for the user including weekly stats.
    TODO: Re-add user authentication once token issue is fixed.
    """
    # Use provided user_id or fall back to first user
    if user_id:
        result = await db.execute(select(User).where(User.id == user_id))
    else:
        result = await db.execute(select(User).limit(1))
    current_user = result.scalar_one_or_none()
    if not current_user:
        return ClockStatusResponse(is_clocked_in=False, hours_worked_today=0)
    
    # Use Australian Eastern Time
    today = get_melbourne_now().date()
    week_start, week_end = get_week_dates(today)
    
    # Get all entries for this week
    result = await db.execute(
        select(TimesheetEntry)
        .join(Timesheet)
        .where(
            Timesheet.worker_id == current_user.id,
            TimesheetEntry.entry_date >= week_start,
            TimesheetEntry.entry_date <= week_end
        )
    )
    week_entries = result.scalars().all()
    
    # Calculate weekly stats from completed entries
    completed_week_entries = [e for e in week_entries if e.clock_out_time is not None]
    week_days_worked = len(set(e.entry_date for e in completed_week_entries))
    week_total_hours = sum(e.total_hours or 0 for e in completed_week_entries)
    week_overtime_hours = sum(e.overtime_hours or 0 for e in completed_week_entries)
    
    # Find active entry (clocked in but not out) - check today AND yesterday for overnight shifts
    yesterday = today - timedelta(days=1)
    active_entry = next(
        (e for e in week_entries if e.entry_date in [today, yesterday] and e.clock_in_time and not e.clock_out_time),
        None
    )
    
    # Calculate hours worked today
    today_entries = [e for e in week_entries if e.entry_date == today]
    today_completed = [e for e in today_entries if e.clock_out_time is not None]
    hours_today = sum(e.total_hours or 0 for e in today_completed)
    
    if active_entry:
        # Add current session hours (use Melbourne time)
        now_melb = get_melbourne_now()
        # Use localize() for proper DST handling instead of replace()
        if active_entry.clock_in_time.tzinfo is None:
            clock_in_aware = MELBOURNE_TZ.localize(active_entry.clock_in_time)
        else:
            clock_in_aware = active_entry.clock_in_time
        hours_so_far = (now_melb - clock_in_aware).total_seconds() / 3600
        # Ensure hours is not negative
        hours_so_far = max(0, hours_so_far)
        hours_today += hours_so_far
        
        # Return timezone-aware ISO string for frontend
        clock_in_time_aware = MELBOURNE_TZ.localize(active_entry.clock_in_time) if active_entry.clock_in_time.tzinfo is None else active_entry.clock_in_time
        
        return ClockStatusResponse(
            is_clocked_in=True,
            clock_in_time=clock_in_time_aware,
            clock_in_address=active_entry.clock_in_address,
            current_entry_id=active_entry.id,
            hours_worked_today=round(hours_today, 2),
            overtime_mode=active_entry.overtime_mode or False,
            week_days_worked=week_days_worked,
            week_total_hours=round(week_total_hours + hours_so_far, 2),
            week_overtime_hours=round(week_overtime_hours, 2)
        )
    
    return ClockStatusResponse(
        is_clocked_in=False,
        hours_worked_today=round(hours_today, 2),
        week_days_worked=week_days_worked,
        week_total_hours=round(week_total_hours, 2),
        week_overtime_hours=round(week_overtime_hours, 2)
    )


@router.post("/overtime-mode")
async def toggle_overtime_mode(
    request: OvertimeModeRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Toggle overtime mode for the current active timesheet entry.
    When overtime mode is enabled, clock-out reminders are suppressed.
    """
    # Use provided user_id or fall back to first user
    if request.user_id:
        result = await db.execute(select(User).where(User.id == request.user_id))
    else:
        result = await db.execute(select(User).limit(1))
    current_user = result.scalar_one_or_none()
    if not current_user:
        raise HTTPException(status_code=400, detail="No user found")
    
    # Use Australian Eastern Time
    today = get_melbourne_now().date()
    yesterday = today - timedelta(days=1)
    
    # Find active entry (clocked in but not out) - check today and yesterday for overnight shifts
    result = await db.execute(
        select(TimesheetEntry)
        .join(Timesheet)
        .where(
            Timesheet.worker_id == current_user.id,
            TimesheetEntry.entry_date.in_([today, yesterday]),
            TimesheetEntry.clock_in_time.isnot(None),
            TimesheetEntry.clock_out_time.is_(None)
        )
    )
    active_entry = result.scalar_one_or_none()
    
    if not active_entry:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active clock-in found. You must be clocked in to enable overtime mode."
        )
    
    # Update overtime mode
    active_entry.overtime_mode = request.overtime_mode
    await db.commit()
    
    return {
        "success": True,
        "overtime_mode": active_entry.overtime_mode,
        "message": f"Overtime mode {'enabled' if request.overtime_mode else 'disabled'}. " +
                   ("Clock-out reminders will be suppressed." if request.overtime_mode else "Clock-out reminders will resume.")
    }


@router.post("/in")
async def clock_in(
    request: ClockInRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Clock in at a job site with GPS location.
    Creates or updates the timesheet entry for today.
    TODO: Re-add authentication once token issue is fixed.
    """
    # Use provided user_id or fall back to first user
    if request.user_id:
        result = await db.execute(select(User).where(User.id == request.user_id))
    else:
        result = await db.execute(select(User).limit(1))
    current_user = result.scalar_one_or_none()
    if not current_user:
        raise HTTPException(status_code=400, detail="No user found")
    
    # Use Australian Eastern Time for all clock operations
    now_melb = get_melbourne_now()
    now = now_melb.replace(tzinfo=None)  # Store as naive datetime for DB compatibility
    today = now_melb.date()
    week_start, week_end = get_week_dates(today)
    
    # Check if already clocked in (check today and yesterday for overnight shifts)
    yesterday = today - timedelta(days=1)
    result = await db.execute(
        select(TimesheetEntry)
        .join(Timesheet)
        .where(
            Timesheet.worker_id == current_user.id,
            TimesheetEntry.entry_date.in_([today, yesterday]),
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
    
    # Priority 1: Use provided job_site_id if valid
    if request.job_site_id:
        result = await db.execute(
            select(JobSite).where(JobSite.id == request.job_site_id)
        )
        job_site = result.scalar_one_or_none()
        if job_site:
            client_id = job_site.client_id
    
    # Priority 2: Auto-detect nearest job site within 1km using GPS
    if not client_id and request.latitude and request.longitude:
        result = await db.execute(
            select(JobSite).where(
                JobSite.is_active == True,
                JobSite.latitude.isnot(None),
                JobSite.longitude.isnot(None)
            )
        )
        all_sites = result.scalars().all()
        
        nearest_site = None
        nearest_distance = float('inf')
        GPS_MATCH_THRESHOLD_KM = 1.0  # 1km threshold
        
        for site in all_sites:
            try:
                distance_km = geodesic(
                    (request.latitude, request.longitude),
                    (site.latitude, site.longitude)
                ).kilometers
                if distance_km <= GPS_MATCH_THRESHOLD_KM and distance_km < nearest_distance:
                    nearest_distance = distance_km
                    nearest_site = site
            except:
                continue
        
        if nearest_site:
            job_site = nearest_site
            client_id = nearest_site.client_id
            print(f"[Clock-in] Auto-detected job site: {nearest_site.name} ({nearest_distance:.2f}km away)")
    
    # Priority 3: Use default "RAW General Site" (ID=1) as fallback
    if not client_id:
        result = await db.execute(
            select(JobSite).where(JobSite.id == 1)
        )
        default_site = result.scalar_one_or_none()
        if default_site:
            job_site = default_site
            client_id = default_site.client_id
            print(f"[Clock-in] Using default job site: {default_site.name}")
    
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
        # Generate unique consecutive docket number
        # Use MAX to get highest existing docket number to ensure no duplicates
        from sqlalchemy import func, cast, Integer
        result = await db.execute(
            select(func.max(cast(Timesheet.docket_number, Integer)))
        )
        max_docket = result.scalar()
        new_docket = str((max_docket or 12537) + 1)
        
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
    
    # Use manual address if provided, otherwise reverse geocode from GPS
    if request.address and request.address.strip():
        clock_in_address = request.address.strip()
    elif request.latitude != 0 and request.longitude != 0:
        clock_in_address = get_address_from_coords(request.latitude, request.longitude)
    else:
        clock_in_address = "Address not provided"
    
    # If worker provided a manual job site address (no job site detected), append it
    if request.job_site_address and request.job_site_address.strip():
        clock_in_address = f"{clock_in_address} | Job Site: {request.job_site_address.strip()}"
    
    # Get assigned shift times from user assignment
    assigned_start = current_user.assignment_start_time  # e.g., "07:00"
    assigned_end = current_user.assignment_end_time  # e.g., "15:30"
    
    # Determine effective clock-in time (round up to shift start if early)
    effective_clock_in = now
    early_arrival_minutes = 0
    
    if assigned_start:
        try:
            start_hour, start_min = map(int, assigned_start.split(':'))
            shift_start_datetime = now.replace(hour=start_hour, minute=start_min, second=0, microsecond=0)
            
            # If clocked in before shift start, use shift start time for hours calculation
            if now < shift_start_datetime:
                early_arrival_minutes = int((shift_start_datetime - now).total_seconds() / 60)
                effective_clock_in = shift_start_datetime
        except (ValueError, AttributeError):
            pass  # Invalid time format, use actual clock-in
    
    # Create timesheet entry
    entry = TimesheetEntry(
        timesheet_id=timesheet.id,
        day_of_week=get_day_of_week(today),
        entry_date=today,
        job_site_id=request.job_site_id,
        time_start=effective_clock_in.time(),  # Use effective time (rounded to shift start if early)
        clock_in_time=now,  # Store actual clock-in time for GPS tracking
        clock_in_latitude=request.latitude if request.latitude != 0 else None,
        clock_in_longitude=request.longitude if request.longitude != 0 else None,
        clock_in_address=clock_in_address,
        worked_as=request.worked_as,
        assigned_start_time=assigned_start,
        assigned_end_time=assigned_end
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    
    # Return timezone-aware ISO string for correct frontend display
    return {
        "message": "Successfully clocked in",
        "entry_id": entry.id,
        "clock_in_time": now_melb.isoformat(),  # Actual clock-in time
        "effective_start_time": MELBOURNE_TZ.localize(effective_clock_in).isoformat(),  # For hours calc
        "clock_in_address": clock_in_address,
        "docket_number": timesheet.docket_number,
        "job_site": job_site.name if job_site else None,
        "assigned_start_time": assigned_start,
        "assigned_end_time": assigned_end,
        "early_arrival_minutes": early_arrival_minutes
    }


@router.post("/out")
async def clock_out(
    request: ClockOutRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Clock out from current job with GPS location.
    Calculates hours worked and updates timesheet.
    TODO: Re-add authentication once token issue is fixed.
    """
    # Use provided user_id or fall back to first user
    if request.user_id:
        result = await db.execute(select(User).where(User.id == request.user_id))
    else:
        result = await db.execute(select(User).limit(1))
    current_user = result.scalar_one_or_none()
    if not current_user:
        raise HTTPException(status_code=400, detail="No user found")
    
    # Use Australian Eastern Time for all clock operations
    now_melb = get_melbourne_now()
    now = now_melb.replace(tzinfo=None)  # Store as naive datetime for DB compatibility
    today = now_melb.date()
    yesterday = today - timedelta(days=1)
    
    # Find active clock-in entry (check today and yesterday for overnight shifts)
    result = await db.execute(
        select(TimesheetEntry)
        .join(Timesheet)
        .where(
            Timesheet.worker_id == current_user.id,
            TimesheetEntry.entry_date.in_([today, yesterday]),
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
    
    # Use manual address if provided, otherwise reverse geocode from GPS
    if request.address and request.address.strip():
        clock_out_address = request.address.strip()
    elif request.latitude != 0 and request.longitude != 0:
        clock_out_address = get_address_from_coords(request.latitude, request.longitude)
    else:
        clock_out_address = "Address not provided"
    
    # Determine effective start and end times for hours calculation
    # Start time: Use time_start (which is already rounded to shift start if early)
    effective_start = entry.time_start
    if entry.clock_in_time:
        # Combine entry_date with time_start for proper datetime
        effective_start_dt = datetime.combine(entry.entry_date, effective_start) if effective_start else entry.clock_in_time
    else:
        effective_start_dt = entry.clock_in_time
    
    # End time: Check if worker is past assigned end time
    effective_end_dt = now
    is_past_shift_end = False
    overtime_minutes = 0
    
    if entry.assigned_end_time and request.is_overtime is False:
        # Worker said they are NOT doing overtime - use assigned end time
        try:
            end_hour, end_min = map(int, entry.assigned_end_time.split(':'))
            shift_end_datetime = now.replace(hour=end_hour, minute=end_min, second=0, microsecond=0)
            
            # Handle overnight shifts (end time is next day)
            if shift_end_datetime < effective_start_dt:
                shift_end_datetime = shift_end_datetime + timedelta(days=1)
            
            if now > shift_end_datetime:
                # Worker clocked out late but not doing overtime
                overtime_minutes = int((now - shift_end_datetime).total_seconds() / 60)
                effective_end_dt = shift_end_datetime
                is_past_shift_end = True
        except (ValueError, AttributeError):
            pass  # Invalid format, use actual clock-out
    elif entry.assigned_end_time:
        # Check if past shift end for info purposes
        try:
            end_hour, end_min = map(int, entry.assigned_end_time.split(':'))
            shift_end_datetime = now.replace(hour=end_hour, minute=end_min, second=0, microsecond=0)
            if shift_end_datetime < effective_start_dt:
                shift_end_datetime = shift_end_datetime + timedelta(days=1)
            if now > shift_end_datetime:
                is_past_shift_end = True
                overtime_minutes = int((now - shift_end_datetime).total_seconds() / 60)
        except (ValueError, AttributeError):
            pass
    
    # Handle overnight shifts - if end time appears to be before start time, add a day
    # This handles cases where worker clocks in at night (e.g., 22:00) and out next morning (e.g., 06:30)
    if effective_end_dt < effective_start_dt:
        effective_end_dt = effective_end_dt + timedelta(days=1)
    
    # Calculate hours with break deduction (default 30 min unpaid)
    unpaid_break = entry.unpaid_break_minutes if entry.unpaid_break_minutes is not None else 30
    ordinary_hours, overtime_hours, gross_hours = calculate_hours(effective_start_dt, effective_end_dt, unpaid_break)
    total_hours = ordinary_hours + overtime_hours
    
    # Update entry
    entry.time_finish = effective_end_dt.time()  # Use effective end time
    entry.clock_out_time = now  # Store actual clock-out for GPS tracking
    entry.clock_out_latitude = request.latitude if request.latitude != 0 else None
    entry.clock_out_longitude = request.longitude if request.longitude != 0 else None
    entry.clock_out_address = clock_out_address
    entry.gross_hours = gross_hours
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
    
    # Return timezone-aware ISO strings for correct frontend display
    clock_in_time_aware = MELBOURNE_TZ.localize(entry.clock_in_time) if entry.clock_in_time.tzinfo is None else entry.clock_in_time
    
    return {
        "message": "Successfully clocked out",
        "entry_id": entry.id,
        "docket_number": timesheet.docket_number,
        "clock_in_time": clock_in_time_aware.isoformat(),
        "clock_out_time": now_melb.isoformat(),  # Actual clock-out time
        "effective_end_time": MELBOURNE_TZ.localize(effective_end_dt).isoformat(),  # Used for hours calc
        "clock_out_address": clock_out_address,
        "gross_hours": gross_hours,  # Hours before break deduction
        "unpaid_break_minutes": unpaid_break,
        "ordinary_hours": ordinary_hours,
        "overtime_hours": overtime_hours,
        "total_hours": total_hours,  # Net hours after break
        "weekly_total": timesheet.total_hours,
        "assigned_end_time": entry.assigned_end_time,
        "was_past_shift_end": is_past_shift_end,
        "late_minutes_ignored": overtime_minutes if request.is_overtime is False else 0
    }


@router.get("/check-overtime")
async def check_overtime_prompt(
    user_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Check if the worker should be prompted for overtime when clocking out.
    Returns whether current time is past their assigned shift end time.
    """
    if user_id:
        result = await db.execute(select(User).where(User.id == user_id))
    else:
        result = await db.execute(select(User).limit(1))
    current_user = result.scalar_one_or_none()
    
    if not current_user:
        return {"should_prompt": False, "reason": "no_user"}
    
    now_melb = get_melbourne_now()
    today = now_melb.date()
    yesterday = today - timedelta(days=1)
    
    # Find active entry
    result = await db.execute(
        select(TimesheetEntry)
        .join(Timesheet)
        .where(
            Timesheet.worker_id == current_user.id,
            TimesheetEntry.entry_date.in_([today, yesterday]),
            TimesheetEntry.clock_in_time.isnot(None),
            TimesheetEntry.clock_out_time.is_(None)
        )
    )
    entry = result.scalar_one_or_none()
    
    if not entry:
        return {"should_prompt": False, "reason": "not_clocked_in"}
    
    assigned_end = entry.assigned_end_time
    if not assigned_end:
        return {"should_prompt": False, "reason": "no_assigned_end_time"}
    
    try:
        end_hour, end_min = map(int, assigned_end.split(':'))
        shift_end = now_melb.replace(hour=end_hour, minute=end_min, second=0, microsecond=0)
        
        # Handle overnight shifts
        if entry.entry_date == yesterday:
            # Entry is from yesterday, so shift end is today
            pass
        elif shift_end.time() < entry.clock_in_time.time():
            # Shift end is earlier than clock in = overnight shift
            shift_end = shift_end + timedelta(days=1)
        
        minutes_past = int((now_melb - shift_end).total_seconds() / 60)
        
        if now_melb > shift_end:
            return {
                "should_prompt": True,
                "assigned_end_time": assigned_end,
                "minutes_past_shift": minutes_past,
                "message": f"Your assigned shift ended at {assigned_end}. Are you working overtime?"
            }
        else:
            return {
                "should_prompt": False,
                "assigned_end_time": assigned_end,
                "minutes_until_end": -minutes_past,
                "reason": "before_shift_end"
            }
    except (ValueError, AttributeError):
        return {"should_prompt": False, "reason": "invalid_end_time_format"}


@router.get("/history")
async def get_clock_history(
    days: int = 7,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get clock in/out history for the user.
    """
    # Use Australian Eastern Time
    today = get_melbourne_now().date()
    start_date = today - timedelta(days=days)
    
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
