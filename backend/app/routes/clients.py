"""
RAW Labour Hire - Clients API
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, List

from ..database import get_db
from ..models import User, Client, JobSite, UserRole
from .auth import get_current_user

router = APIRouter()


class ClientCreate(BaseModel):
    name: str
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    address: Optional[str] = None
    hourly_billing_rate: float = 0
    overtime_billing_rate: float = 0
    weekend_billing_rate: float = 0
    night_billing_rate: float = 0


class JobSiteCreate(BaseModel):
    name: str
    address: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    geofence_radius: int = 100


@router.get("/")
async def list_clients(
    active_only: bool = True,
    db: AsyncSession = Depends(get_db)
):
    """List all clients (no auth for admin dashboard)"""
    query = select(Client)
    if active_only:
        query = query.where(Client.is_active == True)
    
    result = await db.execute(query.order_by(Client.name))
    clients = result.scalars().all()
    
    return {
        "clients": [
            {
                "id": c.id,
                "name": c.name,
                "contact_name": c.contact_name,
                "contact_email": c.contact_email,
                "contact_phone": c.contact_phone,
                "address": c.address,
                "hourly_billing_rate": c.hourly_billing_rate or 0,
                "overtime_billing_rate": c.overtime_billing_rate or 0,
                "weekend_billing_rate": c.weekend_billing_rate or 0,
                "night_billing_rate": c.night_billing_rate or 0,
                "is_active": c.is_active
            }
            for c in clients
        ]
    }


@router.post("/")
async def create_client(
    client_data: ClientCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new client (supervisor/admin only)"""
    if current_user.role == UserRole.WORKER:
        raise HTTPException(status_code=403, detail="Access denied")
    
    client = Client(**client_data.model_dump())
    db.add(client)
    await db.commit()
    await db.refresh(client)
    
    return {"id": client.id, "name": client.name}


@router.post("/admin")
async def create_client_admin(
    client_data: ClientCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new client (admin dashboard - no auth)"""
    client = Client(**client_data.model_dump())
    db.add(client)
    await db.commit()
    await db.refresh(client)
    
    return {"id": client.id, "name": client.name, "message": "Client created successfully"}


@router.put("/admin/{client_id}")
async def update_client_admin(
    client_id: int,
    client_data: ClientCreate,
    db: AsyncSession = Depends(get_db)
):
    """Update a client (admin dashboard - no auth)"""
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    # Update fields
    client.name = client_data.name
    client.contact_name = client_data.contact_name
    client.contact_email = client_data.contact_email
    client.contact_phone = client_data.contact_phone
    client.address = client_data.address
    client.hourly_billing_rate = client_data.hourly_billing_rate
    client.overtime_billing_rate = client_data.overtime_billing_rate
    client.weekend_billing_rate = client_data.weekend_billing_rate
    client.night_billing_rate = client_data.night_billing_rate
    
    await db.commit()
    
    return {"id": client.id, "name": client.name, "message": "Client updated successfully"}


@router.delete("/admin/{client_id}")
async def delete_client_admin(
    client_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Delete a client (admin dashboard - no auth)"""
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    # Soft delete - just deactivate
    client.is_active = False
    await db.commit()
    
    return {"message": "Client deleted successfully"}


@router.get("/{client_id}/job-sites")
async def list_job_sites(
    client_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List job sites for a client"""
    result = await db.execute(
        select(JobSite)
        .where(JobSite.client_id == client_id, JobSite.is_active == True)
        .order_by(JobSite.name)
    )
    sites = result.scalars().all()
    
    return {
        "job_sites": [
            {
                "id": s.id,
                "name": s.name,
                "address": s.address,
                "latitude": s.latitude,
                "longitude": s.longitude,
                "geofence_radius": s.geofence_radius
            }
            for s in sites
        ]
    }


@router.post("/{client_id}/job-sites")
async def create_job_site(
    client_id: int,
    site_data: JobSiteCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new job site for a client"""
    if current_user.role == UserRole.WORKER:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Verify client exists
    result = await db.execute(select(Client).where(Client.id == client_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Client not found")
    
    site = JobSite(client_id=client_id, **site_data.model_dump())
    db.add(site)
    await db.commit()
    await db.refresh(site)
    
    return {"id": site.id, "name": site.name}


@router.get("/job-sites/all")
async def list_all_job_sites(
    db: AsyncSession = Depends(get_db)
):
    """List all active job sites (for clock-in selection) - temporarily no auth for testing"""
    result = await db.execute(
        select(JobSite, Client)
        .join(Client)
        .where(JobSite.is_active == True, Client.is_active == True)
        .order_by(Client.name, JobSite.name)
    )
    rows = result.all()
    
    return {
        "job_sites": [
            {
                "id": site.id,
                "name": site.name,
                "address": site.address,
                "client_id": client.id,
                "client_name": client.name,
                "latitude": site.latitude,
                "longitude": site.longitude
            }
            for site, client in rows
        ]
    }
