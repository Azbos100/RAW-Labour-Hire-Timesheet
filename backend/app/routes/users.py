"""
RAW Labour Hire - Users API (Admin)
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from datetime import date
import hashlib
import secrets

from ..database import get_db
from ..models import User, UserRole
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
    """List all workers for admin dashboard"""
    query = select(User)
    if active_only:
        query = query.where(User.is_active == True)
    
    result = await db.execute(query.order_by(User.surname, User.first_name))
    users = result.scalars().all()
    
    return {
        "workers": [
            {
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
                "created_at": u.created_at.isoformat() if u.created_at else None
            }
            for u in users
        ]
    }


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
