"""
RAW Labour Hire - Clients API
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, List

from ..database import get_db
from ..models import User, Client, JobSite, UserRole, ClientContact
from .auth import get_current_user

router = APIRouter()


class ClientContactCreate(BaseModel):
    name: str
    phone: Optional[str] = None
    role: Optional[str] = None


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
    travel_charge_per_day: float = 0


class JobSiteCreate(BaseModel):
    name: str
    address: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    geofence_radius: int = 100


@router.get("/")
async def list_clients(
    request: Request,
    active_only: bool = True,
    db: AsyncSession = Depends(get_db)
):
    """List all clients. Billing rates are only exposed to admin tokens;
    worker tokens (which use this for the client dropdown) get the names only."""
    is_admin = getattr(request.state, "is_admin", False)

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
                "hourly_billing_rate": (c.hourly_billing_rate or 0) if is_admin else None,
                "overtime_billing_rate": (c.overtime_billing_rate or 0) if is_admin else None,
                "weekend_billing_rate": (c.weekend_billing_rate or 0) if is_admin else None,
                "night_billing_rate": (c.night_billing_rate or 0) if is_admin else None,
                "travel_charge_per_day": (c.travel_charge_per_day or 0) if is_admin else None,
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
    client.travel_charge_per_day = client_data.travel_charge_per_day
    
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


# ==================== CLIENT CONTACTS (FOREMEN) ====================

@router.get("/contacts/all")
async def list_all_client_contacts(
    db: AsyncSession = Depends(get_db)
):
    """List every active client contact (foreman). Used by the admin dashboard."""
    result = await db.execute(
        select(ClientContact)
        .where(ClientContact.is_active == True)
        .order_by(ClientContact.name)
    )
    contacts = result.scalars().all()
    return {
        "contacts": [
            {
                "id": c.id,
                "client_id": c.client_id,
                "name": c.name,
                "phone": c.phone,
                "role": c.role,
            }
            for c in contacts
        ]
    }


@router.post("/{client_id}/contacts")
async def create_client_contact(
    client_id: int,
    contact: ClientContactCreate,
    db: AsyncSession = Depends(get_db)
):
    """Add a site contact / foreman to a client (admin dashboard - no auth)."""
    name = (contact.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Contact name is required")

    result = await db.execute(select(Client).where(Client.id == client_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Client not found")

    new_contact = ClientContact(
        client_id=client_id,
        name=name,
        phone=(contact.phone or "").strip() or None,
        role=(contact.role or "").strip() or None,
    )
    db.add(new_contact)
    await db.commit()
    await db.refresh(new_contact)
    return {
        "id": new_contact.id,
        "client_id": new_contact.client_id,
        "name": new_contact.name,
        "phone": new_contact.phone,
        "role": new_contact.role,
        "message": "Contact added",
    }


@router.delete("/contacts/{contact_id}")
async def delete_client_contact(
    contact_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Remove a client contact / foreman (admin dashboard - no auth)."""
    result = await db.execute(select(ClientContact).where(ClientContact.id == contact_id))
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    contact.is_active = False
    await db.commit()
    return {"message": "Contact removed", "id": contact_id}


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
                "longitude": site.longitude,
                "contact_name": site.contact_name,
                "contact_phone": site.contact_phone
            }
            for site, client in rows
        ]
    }
