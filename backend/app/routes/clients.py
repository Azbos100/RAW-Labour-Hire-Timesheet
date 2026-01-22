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
    default_hourly_rate: float = 0
    default_overtime_rate: float = 0


class JobSiteCreate(BaseModel):
    name: str
    address: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    geofence_radius: int = 100


@router.get("/")
async def list_clients(
    active_only: bool = True,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all clients"""
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
                "default_hourly_rate": c.default_hourly_rate,
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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all active job sites (for clock-in selection)"""
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
