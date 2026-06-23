"""
RAW Labour Hire - Users API (Admin)
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, delete
from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime, timedelta
import secrets

from ..database import get_db
from ..models import (
    User, UserRole, JobSite, TimesheetEntry, Timesheet, Client, AttendanceEvent,
    UserTicket, UserInduction, MYOBExport, NotificationSettings,
)
from .auth import get_current_user, verify_admin_auth, get_password_hash
from ..pii_crypto import encrypt_pii, decrypt_pii

router = APIRouter()


# ==================== MOBILE APP ENDPOINTS ====================

@router.get("/{user_id}")
async def get_user_profile(
    user_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get user profile by ID (for mobile app)"""
    result = await db.execute(select(User).where(User.id == user_id))
    u = result.scalar_one_or_none()
    
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "id": u.id,
        "email": u.email,
        "first_name": u.first_name,
        "surname": u.surname,
        "phone": u.phone,
        "role": u.role.value if u.role else "worker",
        "date_of_birth": u.date_of_birth.isoformat() if u.date_of_birth else None,
        "start_date": u.start_date.isoformat() if u.start_date else None,
        # Address
        "address": u.address,
        "suburb": u.suburb,
        "state": u.state,
        "postcode": u.postcode,
        # Emergency contact
        "emergency_contact_name": u.emergency_contact_name,
        "emergency_contact_phone": u.emergency_contact_phone,
        "emergency_contact_relationship": u.emergency_contact_relationship,
        # Bank details
        "bank_account_name": decrypt_pii(u.bank_account_name),
        "bank_bsb": decrypt_pii(u.bank_bsb),
        "bank_account_number": decrypt_pii(u.bank_account_number),
        "tax_file_number": decrypt_pii(u.tax_file_number),
        # Employment
        "employment_type": u.employment_type or "casual",
        "is_active": u.is_active,
    }


class WorkerCreate(BaseModel):
    email: str
    first_name: str
    surname: str
    phone: Optional[str] = None
    address: Optional[str] = None
    suburb: Optional[str] = None
    state: Optional[str] = None
    postcode: Optional[str] = None
    date_of_birth: Optional[date] = None
    start_date: Optional[date] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    emergency_contact_relationship: Optional[str] = None
    bank_account_name: Optional[str] = None
    bank_bsb: Optional[str] = None
    bank_account_number: Optional[str] = None
    tax_file_number: Optional[str] = None
    base_pay_rate: Optional[float] = 0
    overtime_pay_rate: Optional[float] = 0
    weekend_pay_rate: Optional[float] = 0
    night_pay_rate: Optional[float] = 0
    travel_allowance: Optional[float] = 0
    demo_allowance: Optional[float] = 0
    employment_type: Optional[str] = "casual"
    role: Optional[str] = "worker"


class WorkerUpdate(BaseModel):
    email: Optional[str] = None
    first_name: Optional[str] = None
    surname: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    suburb: Optional[str] = None
    state: Optional[str] = None
    postcode: Optional[str] = None
    date_of_birth: Optional[date] = None
    start_date: Optional[date] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    emergency_contact_relationship: Optional[str] = None
    bank_account_name: Optional[str] = None
    bank_bsb: Optional[str] = None
    bank_account_number: Optional[str] = None
    tax_file_number: Optional[str] = None
    base_pay_rate: Optional[float] = None
    overtime_pay_rate: Optional[float] = None
    weekend_pay_rate: Optional[float] = None
    night_pay_rate: Optional[float] = None
    travel_allowance: Optional[float] = None
    demo_allowance: Optional[float] = None
    employment_type: Optional[str] = None
    role: Optional[str] = None


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Require admin role"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


@router.get("/")
async def list_users(
    role: Optional[str] = None,
    active_only: bool = True,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """List all users (admin only)"""
    query = select(User)
    
    if role:
        query = query.where(User.role == UserRole(role))
    if active_only:
        query = query.where(User.is_active == True)
    
    result = await db.execute(query.order_by(User.surname))
    users = result.scalars().all()
    
    return {
        "users": [
            {
                "id": u.id,
                "email": u.email,
                "first_name": u.first_name,
                "surname": u.surname,
                "phone": u.phone,
                "role": u.role.value,
                "is_active": u.is_active
            }
            for u in users
        ]
    }


# ==================== ADMIN DASHBOARD ENDPOINTS (Requires Admin Auth) ====================

@router.get("/admin/workers")
async def list_all_workers(
    active_only: bool = True,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(verify_admin_auth)
):
    """List all workers for admin dashboard with assignment and clock-in status"""
    from sqlalchemy.orm import selectinload
    
    query = select(User).where(User.is_archived.isnot(True))
    if active_only:
        query = query.where(User.is_active == True)
    
    result = await db.execute(query.order_by(User.surname, User.first_name))
    users = result.scalars().all()
    
    # Get all active clock-ins (entries with clock_in but no clock_out, from today only)
    import pytz
    MELBOURNE_TZ = pytz.timezone('Australia/Melbourne')
    today = datetime.now(MELBOURNE_TZ).date()
    
    active_entries_result = await db.execute(
        select(TimesheetEntry)
        .where(
            TimesheetEntry.clock_in_time.isnot(None),
            TimesheetEntry.clock_out_time.is_(None),
            TimesheetEntry.entry_date == today  # Only today's entries
        )
    )
    active_entries = active_entries_result.scalars().all()
    
    # Create a map of user_id to their active entry (via timesheet)
    from ..models import Timesheet
    clocked_in_users = {}
    for entry in active_entries:
        # Get the timesheet to find user_id
        ts_result = await db.execute(
            select(Timesheet).where(Timesheet.id == entry.timesheet_id)
        )
        ts = ts_result.scalar_one_or_none()
        if ts:
            clocked_in_users[ts.worker_id] = {
                "clock_in_time": entry.clock_in_time.isoformat() if entry.clock_in_time else None,
                "job_site_id": entry.job_site_id
            }
    
    # Load all per-date assignments for these workers
    from ..services.assignment_helpers import load_assignments_map, melbourne_today

    worker_ids = [u.id for u in users]
    assignments_map = await load_assignments_map(db, worker_ids)
    today_assign = melbourne_today()

    workers_data = []
    for u in users:
        worker_assignments = assignments_map.get(u.id, [])
        # Legacy single-slot field: earliest assignment from today onward
        assigned_job = next(
            (a for a in worker_assignments if a.get("assignment_date") and a["assignment_date"] >= today_assign.isoformat()),
            worker_assignments[0] if worker_assignments else None,
        )
        clock_in_status = clocked_in_users.get(u.id)
        
        workers_data.append({
            "id": u.id,
            "email": u.email,
            "first_name": u.first_name,
            "surname": u.surname,
            "phone": u.phone,
            "address": u.address,
            "suburb": u.suburb,
            "state": u.state,
            "postcode": u.postcode,
            "date_of_birth": u.date_of_birth.isoformat() if u.date_of_birth else None,
            "start_date": u.start_date.isoformat() if u.start_date else None,
            "emergency_contact_name": u.emergency_contact_name,
            "emergency_contact_phone": u.emergency_contact_phone,
            "emergency_contact_relationship": u.emergency_contact_relationship,
            "bank_account_name": decrypt_pii(u.bank_account_name),
            "bank_bsb": decrypt_pii(u.bank_bsb),
            "bank_account_number": decrypt_pii(u.bank_account_number),
            "tax_file_number": decrypt_pii(u.tax_file_number),
            "base_pay_rate": u.base_pay_rate or 0,
            "overtime_pay_rate": u.overtime_pay_rate or 0,
            "weekend_pay_rate": u.weekend_pay_rate or 0,
            "night_pay_rate": u.night_pay_rate or 0,
            "travel_allowance": u.travel_allowance or 0,
            "demo_allowance": u.demo_allowance or 0,
            "employment_type": u.employment_type or "casual",
            "role": u.role.value if u.role else "worker",
            "is_active": u.is_active,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            # Shift schedule fields
            "shift_start_time": u.shift_start_time.strftime("%H:%M") if u.shift_start_time else None,
            "shift_end_time": u.shift_end_time.strftime("%H:%M") if u.shift_end_time else None,
            "works_monday": u.works_monday,
            "works_tuesday": u.works_tuesday,
            "works_wednesday": u.works_wednesday,
            "works_thursday": u.works_thursday,
            "works_friday": u.works_friday,
            "works_saturday": u.works_saturday,
            "works_sunday": u.works_sunday,
            # Job assignments (all dates) + legacy single-slot summary
            "assignments": worker_assignments,
            "assigned_job": assigned_job,
            # Clock-in status
            "is_clocked_in": clock_in_status is not None,
            "clock_in_info": clock_in_status,
            # Push notification status
            "has_push_token": bool(u.push_token),
            # App usage: when the worker was last active in the mobile app
            "last_active": u.last_active.isoformat() if getattr(u, "last_active", None) else None
        })
    
    return {"workers": workers_data}


@router.get("/admin/workers/{worker_id}")
async def get_worker(
    worker_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get single worker details"""
    result = await db.execute(select(User).where(User.id == worker_id))
    u = result.scalar_one_or_none()
    
    if not u:
        raise HTTPException(status_code=404, detail="Worker not found")
    
    return {
        "id": u.id,
        "email": u.email,
        "first_name": u.first_name,
        "surname": u.surname,
        "phone": u.phone,
        "address": u.address,
        "suburb": u.suburb,
        "state": u.state,
        "postcode": u.postcode,
        "date_of_birth": u.date_of_birth.isoformat() if u.date_of_birth else None,
        "start_date": u.start_date.isoformat() if u.start_date else None,
        "emergency_contact_name": u.emergency_contact_name,
        "emergency_contact_phone": u.emergency_contact_phone,
        "emergency_contact_relationship": u.emergency_contact_relationship,
        "bank_account_name": decrypt_pii(u.bank_account_name),
        "bank_bsb": decrypt_pii(u.bank_bsb),
        "bank_account_number": decrypt_pii(u.bank_account_number),
        "tax_file_number": decrypt_pii(u.tax_file_number),
        "base_pay_rate": u.base_pay_rate or 0,
        "overtime_pay_rate": u.overtime_pay_rate or 0,
        "weekend_pay_rate": u.weekend_pay_rate or 0,
        "night_pay_rate": u.night_pay_rate or 0,
        "travel_allowance": u.travel_allowance or 0,
        "demo_allowance": u.demo_allowance or 0,
        "employment_type": u.employment_type or "casual",
        "role": u.role.value if u.role else "worker",
        "is_active": u.is_active
    }


@router.post("/admin/workers")
async def create_worker(
    worker: WorkerCreate,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(verify_admin_auth)
):
    """Create a new worker"""
    # Check if email already exists (case-insensitive)
    email_clean = (worker.email or "").strip()
    existing = await db.execute(
        select(User).where(func.lower(User.email) == email_clean.lower())
    )
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Generate a random password (worker will need to reset)
    temp_password = secrets.token_urlsafe(12)
    hashed = get_password_hash(temp_password)
    
    new_worker = User(
        email=worker.email,
        hashed_password=hashed,
        first_name=worker.first_name,
        surname=worker.surname,
        phone=worker.phone,
        address=worker.address,
        suburb=worker.suburb,
        state=worker.state,
        postcode=worker.postcode,
        date_of_birth=worker.date_of_birth,
        start_date=worker.start_date,
        emergency_contact_name=worker.emergency_contact_name,
        emergency_contact_phone=worker.emergency_contact_phone,
        emergency_contact_relationship=worker.emergency_contact_relationship,
        bank_account_name=encrypt_pii(worker.bank_account_name),
        bank_bsb=encrypt_pii(worker.bank_bsb),
        bank_account_number=encrypt_pii(worker.bank_account_number),
        tax_file_number=encrypt_pii(worker.tax_file_number),
        base_pay_rate=worker.base_pay_rate or 0,
        overtime_pay_rate=worker.overtime_pay_rate or 0,
        weekend_pay_rate=worker.weekend_pay_rate or 0,
        night_pay_rate=worker.night_pay_rate or 0,
        travel_allowance=worker.travel_allowance or 0,
        demo_allowance=worker.demo_allowance or 0,
        employment_type=worker.employment_type or "casual",
        role=UserRole(worker.role) if worker.role else UserRole.WORKER,
        is_active=True
    )
    
    db.add(new_worker)
    await db.commit()
    await db.refresh(new_worker)
    
    return {
        "id": new_worker.id,
        "email": new_worker.email,
        "temp_password": temp_password,  # Return this so admin can share with worker
        "message": "Worker created. Share the temporary password with them to log in."
    }


@router.put("/admin/workers/{worker_id}")
async def update_worker(
    worker_id: int,
    worker_data: WorkerUpdate,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(verify_admin_auth)
):
    """Update worker details"""
    result = await db.execute(select(User).where(User.id == worker_id))
    worker = result.scalar_one_or_none()
    
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    
    # Update only the fields the client actually sent. We intentionally do NOT
    # exclude None here: a field present in the payload with a null value means
    # the admin cleared it, so it should be blanked (omitted fields are still
    # left untouched via exclude_unset).
    update_data = worker_data.dict(exclude_unset=True)
    _pii_fields = {"bank_account_name", "bank_bsb", "bank_account_number", "tax_file_number"}
    for field, value in update_data.items():
        if field == "role":
            setattr(worker, field, UserRole(value) if value else worker.role)
        elif field in _pii_fields:
            setattr(worker, field, encrypt_pii(value))
        else:
            setattr(worker, field, value)
    
    await db.commit()
    
    return {"message": "Worker updated successfully"}


@router.patch("/admin/workers/{worker_id}/activate")
async def activate_worker(
    worker_id: int,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(verify_admin_auth)
):
    """Activate a worker"""
    result = await db.execute(select(User).where(User.id == worker_id))
    worker = result.scalar_one_or_none()
    
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    
    worker.is_active = True
    await db.commit()
    
    return {"message": "Worker activated"}


@router.patch("/admin/workers/{worker_id}/deactivate")
async def deactivate_worker_admin(
    worker_id: int,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(verify_admin_auth)
):
    """Deactivate a worker"""
    result = await db.execute(select(User).where(User.id == worker_id))
    worker = result.scalar_one_or_none()
    
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    
    worker.is_active = False
    await db.commit()
    
    return {"message": "Worker deactivated"}


@router.delete("/admin/workers/{worker_id}")
async def delete_worker_admin(
    worker_id: int,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(verify_admin_auth)
):
    """Remove a worker from the Workers directory.

    Only allowed for deactivated workers. If the worker has NO payroll history we
    hard-delete them (and their tickets/inductions/attendance). If they DO have
    timesheets we can't drop the row without destroying that history, so instead
    we archive them: they disappear from the directory while their timesheets
    stay fully intact.
    """
    result = await db.execute(select(User).where(User.id == worker_id))
    worker = result.scalar_one_or_none()

    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    if worker.is_active:
        raise HTTPException(
            status_code=400,
            detail="Deactivate the worker before removing them.",
        )

    # If there is payroll history, archive (hide) rather than hard-delete so the
    # timesheets that reference this worker stay intact.
    ts_count = await db.scalar(
        select(func.count()).select_from(Timesheet).where(Timesheet.worker_id == worker_id)
    )
    if ts_count and ts_count > 0:
        worker.is_archived = True
        worker.is_active = False
        await db.commit()
        return {
            "message": (
                f"{worker.first_name} {worker.surname} removed from the workers list. "
                f"Their {ts_count} timesheet(s) are kept for payroll records."
            ),
            "archived": True,
        }

    # No payroll history -> safe to hard delete.
    # Clear nullable references that point at this user.
    await db.execute(update(Timesheet).where(Timesheet.supervisor_id == worker_id).values(supervisor_id=None))
    await db.execute(update(UserTicket).where(UserTicket.verified_by == worker_id).values(verified_by=None))
    await db.execute(update(MYOBExport).where(MYOBExport.exported_by == worker_id).values(exported_by=None))
    await db.execute(update(NotificationSettings).where(NotificationSettings.allocation_notice_recipient_id == worker_id).values(allocation_notice_recipient_id=None))

    # Delete records owned solely by this worker.
    await db.execute(delete(UserTicket).where(UserTicket.user_id == worker_id))
    await db.execute(delete(UserInduction).where(UserInduction.user_id == worker_id))
    await db.execute(delete(AttendanceEvent).where(AttendanceEvent.worker_id == worker_id))

    await db.delete(worker)
    await db.commit()

    return {"message": "Worker permanently deleted", "archived": False}


class AttendanceCreate(BaseModel):
    event_type: str  # 'sick' or 'no_show'
    event_date: Optional[date] = None
    note: Optional[str] = None


@router.get("/admin/workers/{worker_id}/history")
async def get_worker_history(
    worker_id: int,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(verify_admin_auth)
):
    """Worker job-allocation history (dockets) + sick/no-show attendance summary."""
    result = await db.execute(select(User).where(User.id == worker_id))
    worker = result.scalar_one_or_none()
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    # Job allocation history: all dockets for this worker (incl. archived), newest first
    ts_rows = await db.execute(
        select(Timesheet, Client, JobSite)
        .outerjoin(Client, Timesheet.client_id == Client.id)
        .outerjoin(JobSite, Timesheet.job_site_id == JobSite.id)
        .where(Timesheet.worker_id == worker_id)
        .order_by(Timesheet.week_starting.desc(), Timesheet.id.desc())
    )
    allocations = []
    for ts, client, js in ts_rows.all():
        allocations.append({
            "timesheet_id": ts.id,
            "docket_number": ts.docket_number,
            "client_name": client.name if client else None,
            "job_site_name": js.name if js else None,
            "week_starting": ts.week_starting.isoformat() if ts.week_starting else None,
            "week_ending": ts.week_ending.isoformat() if ts.week_ending else None,
            "status": ts.status.value if hasattr(ts.status, "value") else str(ts.status),
            "total_hours": ts.total_hours or 0,
            "archived": ts.archived_at is not None,
        })

    # Attendance events
    ev_rows = await db.execute(
        select(AttendanceEvent)
        .where(AttendanceEvent.worker_id == worker_id)
        .order_by(AttendanceEvent.event_date.desc(), AttendanceEvent.id.desc())
    )
    events = ev_rows.scalars().all()
    sick = sum(1 for e in events if e.event_type == "sick")
    no_show = sum(1 for e in events if e.event_type == "no_show")

    return {
        "worker": {"id": worker.id, "name": f"{worker.first_name} {worker.surname}"},
        "attendance": {
            "sick_count": sick,
            "no_show_count": no_show,
            "events": [
                {
                    "id": e.id,
                    "event_type": e.event_type,
                    "event_date": e.event_date.isoformat() if e.event_date else None,
                    "note": e.note,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }
                for e in events
            ],
        },
        "allocations": allocations,
    }


@router.post("/admin/workers/{worker_id}/attendance")
async def add_attendance_event(
    worker_id: int,
    data: AttendanceCreate,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(verify_admin_auth)
):
    """Record a sick day or no-show for a worker."""
    if data.event_type not in ("sick", "no_show"):
        raise HTTPException(status_code=400, detail="event_type must be 'sick' or 'no_show'")
    result = await db.execute(select(User).where(User.id == worker_id))
    worker = result.scalar_one_or_none()
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    event = AttendanceEvent(
        worker_id=worker_id,
        event_type=data.event_type,
        event_date=data.event_date or date.today(),
        note=(data.note or "").strip() or None,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return {"message": "Recorded", "id": event.id}


@router.delete("/admin/workers/{worker_id}/attendance/{event_id}")
async def delete_attendance_event(
    worker_id: int,
    event_id: int,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(verify_admin_auth)
):
    """Remove a wrongly-recorded attendance event."""
    result = await db.execute(
        select(AttendanceEvent).where(
            AttendanceEvent.id == event_id,
            AttendanceEvent.worker_id == worker_id,
        )
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    await db.delete(event)
    await db.commit()
    return {"message": "Deleted"}


@router.get("/admin/attendance")
async def list_attendance_by_date(
    day: str,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(verify_admin_auth)
):
    """List sick/no-show events for a specific date (all workers)."""
    try:
        target = date.fromisoformat(day)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid date (expected YYYY-MM-DD)")

    result = await db.execute(
        select(AttendanceEvent, User)
        .join(User, AttendanceEvent.worker_id == User.id)
        .where(AttendanceEvent.event_date == target)
        .order_by(User.surname, User.first_name)
    )
    rows = result.all()
    return {
        "events": [
            {
                "id": ev.id,
                "worker_id": ev.worker_id,
                "worker_name": f"{u.first_name} {u.surname}",
                "event_type": ev.event_type,
                "note": ev.note,
            }
            for ev, u in rows
        ]
    }


@router.get("/admin/attendance/month")
async def list_attendance_by_month(
    year: int,
    month: int,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(verify_admin_auth)
):
    """Sick/no-show events for a whole month, grouped by date (for calendar markers)."""
    if month < 1 or month > 12:
        raise HTTPException(status_code=400, detail="Invalid month")

    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)

    result = await db.execute(
        select(AttendanceEvent, User)
        .join(User, AttendanceEvent.worker_id == User.id)
        .where(AttendanceEvent.event_date >= start, AttendanceEvent.event_date < end)
        .order_by(AttendanceEvent.event_date, User.surname, User.first_name)
    )
    rows = result.all()

    days: dict = {}
    for ev, u in rows:
        key = ev.event_date.isoformat()
        days.setdefault(key, []).append({
            "id": ev.id,
            "worker_id": ev.worker_id,
            "worker_name": f"{u.first_name} {u.surname}",
            "event_type": ev.event_type,
            "note": ev.note,
        })
    return {"days": days}


@router.post("/admin/workers/{worker_id}/reset-password")
async def reset_worker_password(
    worker_id: int,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(verify_admin_auth)
):
    """Reset worker password and return new temporary password"""
    result = await db.execute(select(User).where(User.id == worker_id))
    worker = result.scalar_one_or_none()
    
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    
    # Generate new temporary password
    temp_password = secrets.token_urlsafe(12)
    worker.hashed_password = get_password_hash(temp_password)
    
    await db.commit()
    
    return {
        "temp_password": temp_password,
        "message": "Password reset. Share the new temporary password with the worker."
    }


class ShiftScheduleUpdate(BaseModel):
    shift_start_time: Optional[str] = None  # HH:MM format
    shift_end_time: Optional[str] = None    # HH:MM format
    works_monday: Optional[bool] = None
    works_tuesday: Optional[bool] = None
    works_wednesday: Optional[bool] = None
    works_thursday: Optional[bool] = None
    works_friday: Optional[bool] = None
    works_saturday: Optional[bool] = None
    works_sunday: Optional[bool] = None


@router.patch("/admin/workers/{worker_id}/schedule")
async def update_worker_schedule(
    worker_id: int,
    schedule: ShiftScheduleUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update worker shift schedule for SMS reminders"""
    from datetime import datetime as dt
    
    result = await db.execute(select(User).where(User.id == worker_id))
    worker = result.scalar_one_or_none()
    
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    
    # Update shift times
    if schedule.shift_start_time:
        worker.shift_start_time = dt.strptime(schedule.shift_start_time, "%H:%M").time()
    if schedule.shift_end_time:
        worker.shift_end_time = dt.strptime(schedule.shift_end_time, "%H:%M").time()
    
    # Update work days
    if schedule.works_monday is not None:
        worker.works_monday = schedule.works_monday
    if schedule.works_tuesday is not None:
        worker.works_tuesday = schedule.works_tuesday
    if schedule.works_wednesday is not None:
        worker.works_wednesday = schedule.works_wednesday
    if schedule.works_thursday is not None:
        worker.works_thursday = schedule.works_thursday
    if schedule.works_friday is not None:
        worker.works_friday = schedule.works_friday
    if schedule.works_saturday is not None:
        worker.works_saturday = schedule.works_saturday
    if schedule.works_sunday is not None:
        worker.works_sunday = schedule.works_sunday
    
    await db.commit()
    
    return {
        "message": "Schedule updated",
        "shift_start_time": worker.shift_start_time.strftime("%H:%M") if worker.shift_start_time else None,
        "shift_end_time": worker.shift_end_time.strftime("%H:%M") if worker.shift_end_time else None,
        "works_monday": worker.works_monday,
        "works_tuesday": worker.works_tuesday,
        "works_wednesday": worker.works_wednesday,
        "works_thursday": worker.works_thursday,
        "works_friday": worker.works_friday,
        "works_saturday": worker.works_saturday,
        "works_sunday": worker.works_sunday
    }


# ==================== PUSH NOTIFICATION TOKEN ====================

class PushTokenUpdate(BaseModel):
    push_token: str


@router.post("/{user_id}/push-token")
async def save_push_token(
    user_id: int,
    token_data: PushTokenUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Save push notification token for a user"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        print(f"[Push Token] User {user_id} not found")
        raise HTTPException(status_code=404, detail="User not found")
    
    old_token = user.push_token
    user.push_token = token_data.push_token
    await db.commit()
    
    # Log for debugging
    user_name = f"{user.first_name} {user.surname}"
    if old_token:
        print(f"[Push Token] Updated token for {user_name} (ID: {user_id})")
    else:
        print(f"[Push Token] NEW token registered for {user_name} (ID: {user_id})")
    
    return {"message": "Push token saved", "user": user_name}


# ==================== JOB ASSIGNMENT ENDPOINTS ====================

class JobAssignment(BaseModel):
    job_site_id: Optional[int] = None  # None to clear assignment
    assignment_date: Optional[date] = None  # Date the job is for
    start_time: Optional[str] = None  # Start time for the shift (e.g., "07:00")
    end_time: Optional[str] = None  # End time for the shift (e.g., "15:30")
    contact_name: Optional[str] = None  # Foreman / site contact name
    contact_phone: Optional[str] = None  # Foreman / site contact phone


@router.post("/admin/workers/{worker_id}/assign")
async def assign_worker_to_job(
    worker_id: int,
    assignment: JobAssignment,
    db: AsyncSession = Depends(get_db),
    background_tasks: BackgroundTasks = None,
    admin: dict = Depends(verify_admin_auth)
):
    """Assign a worker to a job site for a specific date (upserts; does not overwrite other days)."""
    from ..services.push_notifications import send_push_notification
    from ..services.sms import send_sms, CONTACT_FOOTER
    from ..services.assignment_helpers import upsert_assignment, delete_assignment

    result = await db.execute(select(User).where(User.id == worker_id))
    worker = result.scalar_one_or_none()

    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    notifications_sent = []

    if assignment.job_site_id:
        js_result = await db.execute(select(JobSite).where(JobSite.id == assignment.job_site_id))
        job_site = js_result.scalar_one_or_none()
        if not job_site:
            raise HTTPException(status_code=404, detail="Job site not found")

        assign_date = assignment.assignment_date or date.today()
        row = await upsert_assignment(
            db,
            worker,
            job_site_id=assignment.job_site_id,
            assignment_date=assign_date,
            start_time=assignment.start_time,
            end_time=assignment.end_time,
            contact_name=assignment.contact_name,
            contact_phone=assignment.contact_phone,
            reset_acceptance=True,
        )

        message = f"Worker assigned to {job_site.name} on {assign_date.strftime('%a %d %b')}"

        date_str = assign_date.strftime("%a %d %b")
        time_str = assignment.start_time or "TBC"
        contact_str = ""
        contact_name = row.contact_name or job_site.contact_name
        contact_phone = row.contact_phone or job_site.contact_phone
        if contact_name:
            contact_str = f" Foreman: {contact_name}"
            if contact_phone:
                contact_str += f" {contact_phone}"
            contact_str += "."

        if worker.phone:
            sms_message = f"RAW Labour Hire: You've been assigned to {job_site.name} on {date_str} at {time_str}. Address: {job_site.address or 'TBC'}.{contact_str} Open the app to accept.\n{CONTACT_FOOTER}"

            async def send_assignment_sms():
                result = await send_sms(worker.phone, sms_message)
                if result.get("success"):
                    print(f"[Assignment] SMS sent to {worker.first_name} {worker.surname}")
                else:
                    print(f"[Assignment] SMS failed for {worker.first_name}: {result.get('error')}")

            if background_tasks:
                background_tasks.add_task(send_assignment_sms)
            else:
                await send_assignment_sms()
            notifications_sent.append("SMS")

        if worker.push_token:
            notification_title = "New Job Assignment"
            notification_body = f"You've been assigned to {job_site.name} on {date_str} at {time_str}. Tap to accept or decline."
            notification_data = {
                "type": "job_assignment",
                "job_site_id": job_site.id,
                "job_site_name": job_site.name,
                "job_site_address": job_site.address or "",
                "assignment_date": assign_date.isoformat(),
                "start_time": time_str,
            }

            async def send_assignment_notification():
                await send_push_notification(
                    worker.push_token,
                    notification_title,
                    notification_body,
                    notification_data,
                )

            if background_tasks:
                background_tasks.add_task(send_assignment_notification)
            else:
                await send_push_notification(
                    worker.push_token,
                    notification_title,
                    notification_body,
                    notification_data,
                )
            notifications_sent.append("Push")
    else:
        if assignment.assignment_date:
            await delete_assignment(db, worker, assignment.assignment_date)
            message = f"Assignment cleared for {assignment.assignment_date.strftime('%a %d %b')}"
        else:
            await delete_assignment(db, worker, None)
            message = "All assignments cleared"

    await db.commit()

    return {
        "message": message,
        "notifications_sent": notifications_sent
    }


@router.post("/admin/workers/assign-bulk")
async def assign_workers_bulk(
    job_site_id: int,
    worker_ids: list[int],
    assignment_date: Optional[date] = None,
    start_time: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    background_tasks: BackgroundTasks = None
):
    """Assign multiple workers to a job site for one date"""
    from ..services.sms import send_sms, CONTACT_FOOTER
    from ..services.push_notifications import send_push_notification
    from ..services.assignment_helpers import upsert_assignment

    js_result = await db.execute(select(JobSite).where(JobSite.id == job_site_id))
    job_site = js_result.scalar_one_or_none()
    if not job_site:
        raise HTTPException(status_code=404, detail="Job site not found")

    result = await db.execute(select(User).where(User.id.in_(worker_ids)))
    workers = result.scalars().all()

    assigned_count = 0
    sms_sent = 0
    push_sent = 0

    assign_date = assignment_date or date.today()
    date_str = assign_date.strftime("%a %d %b")
    time_str = start_time or "TBC"

    for worker in workers:
        await upsert_assignment(
            db,
            worker,
            job_site_id=job_site_id,
            assignment_date=assign_date,
            start_time=start_time,
            end_time=None,
            contact_name=None,
            contact_phone=None,
            reset_acceptance=True,
        )
        assigned_count += 1

        if worker.phone:
            sms_message = f"RAW Labour Hire: You've been assigned to {job_site.name} on {date_str} at {time_str}. Address: {job_site.address or 'TBC'}. Open the app to accept.\n{CONTACT_FOOTER}"

            async def send_worker_sms(phone=worker.phone, msg=sms_message):
                await send_sms(phone, msg)

            if background_tasks:
                background_tasks.add_task(send_worker_sms)
            sms_sent += 1

        if worker.push_token:
            notification_title = "New Job Assignment"
            notification_body = f"You've been assigned to {job_site.name} on {date_str} at {time_str}. Tap to accept or decline."

            async def send_worker_push(token=worker.push_token, title=notification_title, body=notification_body):
                await send_push_notification(
                    token, title, body,
                    {"type": "job_assignment", "assignment_date": assign_date.isoformat()},
                )

            if background_tasks:
                background_tasks.add_task(send_worker_push)
            push_sent += 1

    await db.commit()

    return {
        "message": f"{assigned_count} workers assigned to {job_site.name}",
        "assigned_count": assigned_count,
        "sms_sent": sms_sent,
        "push_sent": push_sent
    }


# Mobile app endpoint to accept/decline assignment
class AssignmentResponse(BaseModel):
    accepted: bool
    assignment_date: Optional[date] = None


@router.post("/{user_id}/assignment/respond")
async def respond_to_assignment(
    user_id: int,
    response: AssignmentResponse,
    db: AsyncSession = Depends(get_db)
):
    """Worker accepts or declines a job assignment for a specific date."""
    from ..models import WorkerAssignment
    from ..services.assignment_helpers import sync_user_legacy_fields, melbourne_today

    result = await db.execute(select(User).where(User.id == user_id))
    worker = result.scalar_one_or_none()

    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    target_date = response.assignment_date
    if target_date is None:
        today = melbourne_today()
        row = (await db.execute(
            select(WorkerAssignment)
            .where(
                WorkerAssignment.worker_id == worker.id,
                WorkerAssignment.assignment_date >= today,
            )
            .order_by(WorkerAssignment.assignment_date)
            .limit(1)
        )).scalar_one_or_none()
    else:
        row = (await db.execute(
            select(WorkerAssignment).where(
                WorkerAssignment.worker_id == worker.id,
                WorkerAssignment.assignment_date == target_date,
            )
        )).scalar_one_or_none()

    if not row:
        raise HTTPException(status_code=400, detail="No job assignment to respond to")

    row.accepted = response.accepted
    await sync_user_legacy_fields(db, worker)
    await db.commit()

    return {
        "message": "Job accepted" if response.accepted else "Job declined",
        "accepted": response.accepted,
        "assignment_date": row.assignment_date.isoformat(),
    }


@router.get("/{user_id}/assignment")
async def get_worker_assignment(
    user_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get worker job assignments for the mobile app."""
    from ..services.assignment_helpers import get_mobile_assignments

    result = await db.execute(select(User).where(User.id == user_id))
    worker = result.scalar_one_or_none()

    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    return await get_mobile_assignments(db, user_id)


# ==================== ORIGINAL ADMIN AUTH ENDPOINTS ====================

@router.patch("/{user_id}/role")
async def update_user_role(
    user_id: int,
    role: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update a user's role (admin only)"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.role = UserRole(role)
    await db.commit()
    
    return {"message": f"User role updated to {role}"}


@router.patch("/{user_id}/deactivate")
async def deactivate_user(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Deactivate a user (admin only)"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.is_active = False
    await db.commit()
    
    return {"message": "User deactivated"}


# ==================== FORCE CLOCK OUT (ADMIN) ====================

@router.post("/admin/workers/{worker_id}/force-clock-out")
async def force_clock_out_worker(
    worker_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Force clock out a worker who has stale clock-in entries (admin only)"""
    import pytz
    MELBOURNE_TZ = pytz.timezone('Australia/Melbourne')
    
    # Find all active clock-in entries for this worker
    from ..models import Timesheet, TimesheetEntry
    
    # Get all timesheets for this worker
    ts_result = await db.execute(
        select(Timesheet).where(Timesheet.worker_id == worker_id)
    )
    timesheets = ts_result.scalars().all()
    timesheet_ids = [t.id for t in timesheets]
    
    if not timesheet_ids:
        return {"message": "No timesheets found for this worker", "entries_closed": 0}
    
    # Find all entries with clock_in but no clock_out
    entries_result = await db.execute(
        select(TimesheetEntry).where(
            TimesheetEntry.timesheet_id.in_(timesheet_ids),
            TimesheetEntry.clock_in_time.isnot(None),
            TimesheetEntry.clock_out_time.is_(None)
        )
    )
    open_entries = entries_result.scalars().all()
    
    if not open_entries:
        return {"message": "No open clock-in entries found", "entries_closed": 0}
    
    # Close all open entries with current time
    now_melb = datetime.now(MELBOURNE_TZ)
    closed_count = 0
    affected_timesheets = set()
    
    from .clock import calculate_hours

    now_naive = now_melb.replace(tzinfo=None)
    for entry in open_entries:
        # Set clock out to current time
        entry.clock_out_time = now_naive
        entry.clock_out_address = "Force clocked out by admin"
        
        # Calculate hours using the same rules as a normal clock-out
        # (unpaid break deduction for 4h+ shifts, ordinary/overtime split at 8h).
        if entry.clock_in_time:
            unpaid_break = entry.unpaid_break_minutes if entry.unpaid_break_minutes is not None else 30
            ordinary_hours, overtime_hours, gross_hours = calculate_hours(
                entry.clock_in_time, now_naive, unpaid_break
            )
            entry.gross_hours = gross_hours
            entry.ordinary_hours = ordinary_hours
            entry.overtime_hours = overtime_hours
            entry.total_hours = round(ordinary_hours + overtime_hours, 2)
            entry.time_finish = now_naive.time()
        
        affected_timesheets.add(entry.timesheet_id)
        closed_count += 1
    
    # Update timesheet totals for all affected timesheets
    for ts_id in affected_timesheets:
        # Get all entries for this timesheet
        all_entries_result = await db.execute(
            select(TimesheetEntry).where(TimesheetEntry.timesheet_id == ts_id)
        )
        all_entries = all_entries_result.scalars().all()
        
        # Get the timesheet and update totals
        ts_result = await db.execute(select(Timesheet).where(Timesheet.id == ts_id))
        timesheet = ts_result.scalar_one_or_none()
        if timesheet:
            timesheet.total_ordinary_hours = sum(e.ordinary_hours or 0 for e in all_entries)
            timesheet.total_overtime_hours = sum(e.overtime_hours or 0 for e in all_entries)
            timesheet.total_hours = timesheet.total_ordinary_hours + timesheet.total_overtime_hours
    
    await db.commit()
    
    return {
        "message": f"Force clocked out {closed_count} open entries",
        "entries_closed": closed_count
    }


@router.post("/admin/recalculate-timesheet-totals")
async def recalculate_all_timesheet_totals(
    db: AsyncSession = Depends(get_db)
):
    """Recalculate totals for all timesheets based on their entries (admin fix)"""
    from ..models import Timesheet, TimesheetEntry
    
    # Get all timesheets
    ts_result = await db.execute(select(Timesheet))
    timesheets = ts_result.scalars().all()
    
    updated_count = 0
    for timesheet in timesheets:
        # Get all entries for this timesheet
        entries_result = await db.execute(
            select(TimesheetEntry).where(TimesheetEntry.timesheet_id == timesheet.id)
        )
        entries = entries_result.scalars().all()
        
        # Calculate totals
        old_total = timesheet.total_hours or 0
        timesheet.total_ordinary_hours = sum(e.ordinary_hours or 0 for e in entries)
        timesheet.total_overtime_hours = sum(e.overtime_hours or 0 for e in entries)
        timesheet.total_hours = timesheet.total_ordinary_hours + timesheet.total_overtime_hours
        
        if old_total != timesheet.total_hours:
            updated_count += 1
    
    await db.commit()
    
    return {
        "message": f"Recalculated totals for {len(timesheets)} timesheets, {updated_count} had incorrect totals",
        "total_timesheets": len(timesheets),
        "updated": updated_count
    }
