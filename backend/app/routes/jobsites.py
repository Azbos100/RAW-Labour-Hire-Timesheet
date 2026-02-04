"""
RAW Labour Hire - Job Sites API
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional

from ..database import get_db
from ..models import Client, JobSite

router = APIRouter()


class JobSiteCreate(BaseModel):
    name: str
    address: str
    client_id: Optional[int] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    geofence_radius: int = 100


@router.get("")
async def list_all_job_sites(
    db: AsyncSession = Depends(get_db)
):
    """List all job sites for admin dashboard"""
    result = await db.execute(
        select(JobSite).order_by(JobSite.name)
    )
    sites = result.scalars().all()
    
    return {
        "job_sites": [
            {
                "id": s.id,
                "name": s.name,
                "address": s.address,
                "client_id": s.client_id,
                "contact_name": s.contact_name,
                "contact_phone": s.contact_phone,
                "latitude": s.latitude,
                "longitude": s.longitude,
                "geofence_radius": s.geofence_radius,
                "is_active": s.is_active
            }
            for s in sites
        ]
    }


@router.post("")
async def create_job_site(
    site_data: JobSiteCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new job site"""
    # If client_id provided, verify it exists
    if site_data.client_id:
        result = await db.execute(select(Client).where(Client.id == site_data.client_id))
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Client not found")
    
    site = JobSite(
        name=site_data.name,
        address=site_data.address,
        client_id=site_data.client_id,
        contact_name=site_data.contact_name,
        contact_phone=site_data.contact_phone,
        latitude=site_data.latitude,
        longitude=site_data.longitude,
        geofence_radius=site_data.geofence_radius
    )
    db.add(site)
    await db.commit()
    await db.refresh(site)
    
    return {"id": site.id, "name": site.name, "message": "Job site created successfully"}


@router.patch("/{site_id}/deactivate")
async def deactivate_job_site(
    site_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Deactivate a job site"""
    result = await db.execute(select(JobSite).where(JobSite.id == site_id))
    site = result.scalar_one_or_none()
    
    if not site:
        raise HTTPException(status_code=404, detail="Job site not found")
    
    site.is_active = False
    await db.commit()
    
    return {"message": "Job site deactivated"}


@router.patch("/{site_id}/activate")
async def activate_job_site(
    site_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Activate a job site"""
    result = await db.execute(select(JobSite).where(JobSite.id == site_id))
    site = result.scalar_one_or_none()
    
    if not site:
        raise HTTPException(status_code=404, detail="Job site not found")
    
    site.is_active = True
    await db.commit()
    
    return {"message": "Job site activated"}


@router.put("/{site_id}")
async def update_job_site(
    site_id: int,
    site_data: JobSiteCreate,
    db: AsyncSession = Depends(get_db)
):
    """Update a job site"""
    result = await db.execute(select(JobSite).where(JobSite.id == site_id))
    site = result.scalar_one_or_none()
    
    if not site:
        raise HTTPException(status_code=404, detail="Job site not found")
    
    # If client_id provided, verify it exists
    if site_data.client_id:
        client_result = await db.execute(select(Client).where(Client.id == site_data.client_id))
        if not client_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Client not found")
    
    # Update fields
    site.name = site_data.name
    site.address = site_data.address
    site.client_id = site_data.client_id
    site.contact_name = site_data.contact_name
    site.contact_phone = site_data.contact_phone
    site.latitude = site_data.latitude
    site.longitude = site_data.longitude
    site.geofence_radius = site_data.geofence_radius
    
    await db.commit()
    
    return {"id": site.id, "name": site.name, "message": "Job site updated successfully"}


@router.delete("/{site_id}")
async def delete_job_site(
    site_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Delete a job site permanently"""
    result = await db.execute(select(JobSite).where(JobSite.id == site_id))
    site = result.scalar_one_or_none()
    
    if not site:
        raise HTTPException(status_code=404, detail="Job site not found")
    
    await db.delete(site)
    await db.commit()
    
    return {"message": "Job site deleted"}
