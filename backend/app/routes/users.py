"""
RAW Labour Hire - Users API (Admin)
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime
import hashlib
import secrets

from ..database import get_db
from ..models import User, UserRole, JobSite, TimesheetEntry
from .auth import get_current_user

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
        "bank_account_name": u.bank_account_name,
        "bank_bsb": u.bank_bsb,
        "bank_account_number": u.bank_account_number,
        "tax_file_number": u.tax_file_number,
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
    employment_type: Optional[str] = "casual"
    role: Optional[str] = "worker"


class WorkerUpdate(BaseModel):
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


# ==================== ADMIN DASHBOARD ENDPOINTS (No Auth) ====================

@router.get("/admin/workers")
async def list_all_workers(
    active_only: bool = True,
    db: AsyncSession = Depends(get_db)
):
    """List all workers for admin dashboard with assignment and clock-in status"""
    from sqlalchemy.orm import selectinload
    
    query = select(User)
    if active_only:
        query = query.where(User.is_active == True)
    
    result = await db.execute(query.order_by(User.surname, User.first_name))
    users = result.scalars().all()
    
    # Get all active clock-ins (entries with clock_in but no clock_out)
    today = date.today()
    active_entries_result = await db.execute(
        select(TimesheetEntry)
        .where(
            TimesheetEntry.clock_in_time.isnot(None),
            TimesheetEntry.clock_out_time.is_(None)
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
    
    # Get job site names for assigned workers
    job_site_ids = [u.assigned_job_site_id for u in users if hasattr(u, 'assigned_job_site_id') and u.assigned_job_site_id]
    job_sites_map = {}
    if job_site_ids:
        js_result = await db.execute(select(JobSite).where(JobSite.id.in_(job_site_ids)))
        for js in js_result.scalars().all():
            job_sites_map[js.id] = {"name": js.name, "address": js.address}
    
    workers_data = []
    for u in users:
        # Check for assignment info
        assigned_job = None
        if hasattr(u, 'assigned_job_site_id') and u.assigned_job_site_id:
            js_info = job_sites_map.get(u.assigned_job_site_id, {})
            assigned_job = {
                "job_site_id": u.assigned_job_site_id,
                "job_site_name": js_info.get("name", "Unknown"),
                "job_site_address": js_info.get("address", ""),
                "accepted": getattr(u, 'assignment_accepted', None),
                "assignment_date": u.assignment_date.isoformat() if hasattr(u, 'assignment_date') and u.assignment_date else None,
                "assigned_at": u.assigned_at.isoformat() if hasattr(u, 'assigned_at') and u.assigned_at else None
            }
        
        # Check clock-in status
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
            "bank_account_name": u.bank_account_name,
            "bank_bsb": u.bank_bsb,
            "bank_account_number": u.bank_account_number,
            "tax_file_number": u.tax_file_number,
            "base_pay_rate": u.base_pay_rate or 0,
            "overtime_pay_rate": u.overtime_pay_rate or 0,
            "weekend_pay_rate": u.weekend_pay_rate or 0,
            "night_pay_rate": u.night_pay_rate or 0,
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
            # New: Job assignment
            "assigned_job": assigned_job,
            # New: Clock-in status
            "is_clocked_in": clock_in_status is not None,
            "clock_in_info": clock_in_status
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
        "bank_account_name": u.bank_account_name,
        "bank_bsb": u.bank_bsb,
        "bank_account_number": u.bank_account_number,
        "tax_file_number": u.tax_file_number,
        "base_pay_rate": u.base_pay_rate or 0,
        "overtime_pay_rate": u.overtime_pay_rate or 0,
        "weekend_pay_rate": u.weekend_pay_rate or 0,
        "night_pay_rate": u.night_pay_rate or 0,
        "employment_type": u.employment_type or "casual",
        "role": u.role.value if u.role else "worker",
        "is_active": u.is_active
    }


@router.post("/admin/workers")
async def create_worker(
    worker: WorkerCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new worker"""
    # Check if email already exists
    existing = await db.execute(select(User).where(User.email == worker.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Generate a random password (worker will need to reset)
    temp_password = secrets.token_urlsafe(12)
    hashed = hashlib.sha256(temp_password.encode()).hexdigest()
    
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
        bank_account_name=worker.bank_account_name,
        bank_bsb=worker.bank_bsb,
        bank_account_number=worker.bank_account_number,
        tax_file_number=worker.tax_file_number,
        base_pay_rate=worker.base_pay_rate or 0,
        overtime_pay_rate=worker.overtime_pay_rate or 0,
        weekend_pay_rate=worker.weekend_pay_rate or 0,
        night_pay_rate=worker.night_pay_rate or 0,
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
    db: AsyncSession = Depends(get_db)
):
    """Update worker details"""
    result = await db.execute(select(User).where(User.id == worker_id))
    worker = result.scalar_one_or_none()
    
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    
    # Update only provided fields
    update_data = worker_data.dict(exclude_unset=True, exclude_none=True)
    for field, value in update_data.items():
        if field == "role":
            setattr(worker, field, UserRole(value))
        else:
            setattr(worker, field, value)
    
    await db.commit()
    
    return {"message": "Worker updated successfully"}


@router.patch("/admin/workers/{worker_id}/activate")
async def activate_worker(
    worker_id: int,
    db: AsyncSession = Depends(get_db)
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
    db: AsyncSession = Depends(get_db)
):
    """Deactivate a worker"""
    result = await db.execute(select(User).where(User.id == worker_id))
    worker = result.scalar_one_or_none()
    
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    
    worker.is_active = False
    await db.commit()
    
    return {"message": "Worker deactivated"}


@router.post("/admin/workers/{worker_id}/reset-password")
async def reset_worker_password(
    worker_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Reset worker password and return new temporary password"""
    result = await db.execute(select(User).where(User.id == worker_id))
    worker = result.scalar_one_or_none()
    
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    
    # Generate new temporary password
    temp_password = secrets.token_urlsafe(12)
    worker.hashed_password = hashlib.sha256(temp_password.encode()).hexdigest()
    
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


# ==================== JOB ASSIGNMENT ENDPOINTS ====================

class JobAssignment(BaseModel):
    job_site_id: Optional[int] = None  # None to clear assignment
    assignment_date: Optional[date] = None  # Date the job is for


@router.post("/admin/workers/{worker_id}/assign")
async def assign_worker_to_job(
    worker_id: int,
    assignment: JobAssignment,
    db: AsyncSession = Depends(get_db)
):
    """Assign a worker to a job site"""
    result = await db.execute(select(User).where(User.id == worker_id))
    worker = result.scalar_one_or_none()
    
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    
    if assignment.job_site_id:
        # Verify job site exists
        js_result = await db.execute(select(JobSite).where(JobSite.id == assignment.job_site_id))
        job_site = js_result.scalar_one_or_none()
        if not job_site:
            raise HTTPException(status_code=404, detail="Job site not found")
        
        worker.assigned_job_site_id = assignment.job_site_id
        worker.assignment_date = assignment.assignment_date or date.today()
        worker.assignment_accepted = None  # Reset acceptance status
        worker.assigned_at = datetime.utcnow()
        
        message = f"Worker assigned to {job_site.name}"
    else:
        # Clear assignment
        worker.assigned_job_site_id = None
        worker.assignment_date = None
        worker.assignment_accepted = None
        worker.assigned_at = None
        message = "Assignment cleared"
    
    await db.commit()
    
    return {"message": message}


@router.post("/admin/workers/assign-bulk")
async def assign_workers_bulk(
    job_site_id: int,
    worker_ids: list[int],
    assignment_date: Optional[date] = None,
    db: AsyncSession = Depends(get_db)
):
    """Assign multiple workers to a job site"""
    # Verify job site exists
    js_result = await db.execute(select(JobSite).where(JobSite.id == job_site_id))
    job_site = js_result.scalar_one_or_none()
    if not job_site:
        raise HTTPException(status_code=404, detail="Job site not found")
    
    # Get all workers
    result = await db.execute(select(User).where(User.id.in_(worker_ids)))
    workers = result.scalars().all()
    
    assigned_count = 0
    for worker in workers:
        worker.assigned_job_site_id = job_site_id
        worker.assignment_date = assignment_date or date.today()
        worker.assignment_accepted = None
        worker.assigned_at = datetime.utcnow()
        assigned_count += 1
    
    await db.commit()
    
    return {
        "message": f"{assigned_count} workers assigned to {job_site.name}",
        "assigned_count": assigned_count
    }


# Mobile app endpoint to accept/decline assignment
class AssignmentResponse(BaseModel):
    accepted: bool


@router.post("/{user_id}/assignment/respond")
async def respond_to_assignment(
    user_id: int,
    response: AssignmentResponse,
    db: AsyncSession = Depends(get_db)
):
    """Worker accepts or declines their job assignment"""
    result = await db.execute(select(User).where(User.id == user_id))
    worker = result.scalar_one_or_none()
    
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    
    if not worker.assigned_job_site_id:
        raise HTTPException(status_code=400, detail="No job assignment to respond to")
    
    worker.assignment_accepted = response.accepted
    await db.commit()
    
    return {
        "message": "Job accepted" if response.accepted else "Job declined",
        "accepted": response.accepted
    }


@router.get("/{user_id}/assignment")
async def get_worker_assignment(
    user_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get worker's current job assignment (for mobile app)"""
    result = await db.execute(select(User).where(User.id == user_id))
    worker = result.scalar_one_or_none()
    
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    
    if not worker.assigned_job_site_id:
        return {"assignment": None}
    
    # Get job site details
    js_result = await db.execute(select(JobSite).where(JobSite.id == worker.assigned_job_site_id))
    job_site = js_result.scalar_one_or_none()
    
    if not job_site:
        return {"assignment": None}
    
    return {
        "assignment": {
            "job_site_id": job_site.id,
            "job_site_name": job_site.name,
            "job_site_address": job_site.address,
            "assignment_date": worker.assignment_date.isoformat() if worker.assignment_date else None,
            "assigned_at": worker.assigned_at.isoformat() if worker.assigned_at else None,
            "accepted": worker.assignment_accepted
        }
    }


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
