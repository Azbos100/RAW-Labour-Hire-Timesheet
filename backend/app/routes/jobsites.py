"""
RAW Labour Hire - Job Sites API
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, delete
from pydantic import BaseModel
from typing import Optional, List
import json

from ..database import get_db
from ..models import Client, JobSite, User, Timesheet, TimesheetEntry

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
    required_ticket_type_ids: Optional[List[int]] = None


def _parse_required_tickets(raw) -> list:
    """Parse the stored JSON list of required ticket type ids."""
    if not raw:
        return []
    try:
        val = json.loads(raw)
        return [int(x) for x in val] if isinstance(val, list) else []
    except (ValueError, TypeError):
        return []


@router.get("")
async def list_all_job_sites(
    db: AsyncSession = Depends(get_db)
):
    """List all job sites (incl. inactive) for the admin dashboard."""
    result = await db.execute(
        select(JobSite, Client)
        .outerjoin(Client, JobSite.client_id == Client.id)
        .order_by(JobSite.name)
    )
    rows = result.all()
    
    return {
        "job_sites": [
            {
                "id": s.id,
                "name": s.name,
                "address": s.address,
                "client_id": s.client_id,
                "client_name": c.name if c else None,
                "contact_name": s.contact_name,
                "contact_phone": s.contact_phone,
                "latitude": s.latitude,
                "longitude": s.longitude,
                "geofence_radius": s.geofence_radius,
                "required_ticket_type_ids": _parse_required_tickets(s.required_ticket_type_ids),
                "is_active": s.is_active
            }
            for s, c in rows
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
        geofence_radius=site_data.geofence_radius,
        required_ticket_type_ids=json.dumps(site_data.required_ticket_type_ids or [])
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
    if site_data.required_ticket_type_ids is not None:
        site.required_ticket_type_ids = json.dumps(site_data.required_ticket_type_ids)
    
    await db.commit()
    
    return {"id": site.id, "name": site.name, "message": "Job site updated successfully"}


@router.delete("/{site_id}")
async def delete_job_site(
    site_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Delete a job site.

    A job site can be referenced by currently-assigned workers and by historical
    timesheets/entries. We first unassign any workers pointing at this site, then:
      - If the site has NO timesheet history, hard-delete it.
      - If it DOES have history, soft-delete it (is_active=False) so existing
        dockets keep their job-site link instead of breaking foreign keys.
    """
    result = await db.execute(select(JobSite).where(JobSite.id == site_id))
    site = result.scalar_one_or_none()

    if not site:
        raise HTTPException(status_code=404, detail="Job site not found")

    # Unassign any workers currently assigned to this site.
    from ..models import WorkerAssignment
    await db.execute(delete(WorkerAssignment).where(WorkerAssignment.job_site_id == site_id))
    await db.execute(
        update(User)
        .where(User.assigned_job_site_id == site_id)
        .values(
            assigned_job_site_id=None,
            assignment_date=None,
            assignment_start_time=None,
            assignment_end_time=None,
            assignment_contact_name=None,
            assignment_contact_phone=None,
            assignment_accepted=None,
            assigned_at=None,
        )
    )

    # Is the site referenced by any timesheet history?
    ts_count = await db.execute(
        select(func.count(Timesheet.id)).where(Timesheet.job_site_id == site_id)
    )
    entry_count = await db.execute(
        select(func.count(TimesheetEntry.id)).where(TimesheetEntry.job_site_id == site_id)
    )
    has_history = (ts_count.scalar() or 0) > 0 or (entry_count.scalar() or 0) > 0

    if has_history:
        # Preserve history: archive instead of hard delete.
        site.is_active = False
        await db.commit()
        return {
            "message": "Job site archived (it has timesheet history, so it was deactivated rather than deleted).",
            "archived": True,
        }

    await db.delete(site)
    await db.commit()
    return {"message": "Job site deleted", "archived": False}
