"""
RAW Labour Hire - Tickets/Certifications API
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from datetime import datetime, date
from typing import Optional, List

from ..database import get_db
from ..models import User, TicketType, UserTicket

router = APIRouter()


# ============ PYDANTIC MODELS ============

class TicketTypeResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    has_expiry: bool


class UploadTicketRequest(BaseModel):
    ticket_type_id: int
    ticket_number: Optional[str] = None
    issue_date: Optional[str] = None  # ISO format date
    expiry_date: Optional[str] = None  # ISO format date
    front_image: str  # Base64 encoded
    back_image: Optional[str] = None  # Base64 encoded


class UserTicketResponse(BaseModel):
    id: int
    ticket_type_id: int
    ticket_type_name: str
    ticket_number: Optional[str]
    issue_date: Optional[str]
    expiry_date: Optional[str]
    front_image: Optional[str]
    back_image: Optional[str]
    status: str
    is_expired: bool
    created_at: str


# ============ ENDPOINTS ============

@router.get("/types")
async def get_ticket_types(
    db: AsyncSession = Depends(get_db)
):
    """Get all available ticket types"""
    result = await db.execute(
        select(TicketType).where(TicketType.is_active == True).order_by(TicketType.name)
    )
    ticket_types = result.scalars().all()
    
    return {
        "ticket_types": [
            {
                "id": tt.id,
                "name": tt.name,
                "description": tt.description,
                "has_expiry": tt.has_expiry
            }
            for tt in ticket_types
        ]
    }


@router.get("/my-tickets")
async def get_my_tickets(
    user_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get current user's tickets"""
    # Use provided user_id or fall back to first user (temp auth bypass)
    if user_id:
        result = await db.execute(select(User).where(User.id == user_id))
    else:
        result = await db.execute(select(User).limit(1))
    current_user = result.scalar_one_or_none()
    
    if not current_user:
        return {"tickets": []}
    
    result = await db.execute(
        select(UserTicket)
        .where(UserTicket.user_id == current_user.id)
        .order_by(UserTicket.created_at.desc())
    )
    tickets = result.scalars().all()
    
    today = date.today()
    ticket_data = []
    
    for ticket in tickets:
        # Get ticket type
        type_result = await db.execute(
            select(TicketType).where(TicketType.id == ticket.ticket_type_id)
        )
        ticket_type = type_result.scalar_one_or_none()
        
        # Check if expired
        is_expired = False
        if ticket.expiry_date and ticket.expiry_date < today:
            is_expired = True
            # Update status if not already marked
            if ticket.status != "expired":
                ticket.status = "expired"
                await db.commit()
        
        ticket_data.append({
            "id": ticket.id,
            "ticket_type_id": ticket.ticket_type_id,
            "ticket_type_name": ticket_type.name if ticket_type else "Unknown",
            "ticket_number": ticket.ticket_number,
            "issue_date": ticket.issue_date.isoformat() if ticket.issue_date else None,
            "expiry_date": ticket.expiry_date.isoformat() if ticket.expiry_date else None,
            "front_image": ticket.front_image,
            "back_image": ticket.back_image,
            "status": ticket.status,
            "is_expired": is_expired,
            "created_at": ticket.created_at.isoformat()
        })
    
    return {"tickets": ticket_data}


@router.post("/upload")
async def upload_ticket(
    request: UploadTicketRequest,
    user_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    """Upload a new ticket/certification"""
    # Use provided user_id or fall back to first user (temp auth bypass)
    if user_id:
        result = await db.execute(select(User).where(User.id == user_id))
    else:
        result = await db.execute(select(User).limit(1))
    current_user = result.scalar_one_or_none()
    
    if not current_user:
        raise HTTPException(status_code=401, detail="User not found")
    
    # Verify ticket type exists
    type_result = await db.execute(
        select(TicketType).where(TicketType.id == request.ticket_type_id)
    )
    ticket_type = type_result.scalar_one_or_none()
    
    if not ticket_type:
        raise HTTPException(status_code=404, detail="Ticket type not found")
    
    # Parse dates - handle multiple formats
    def parse_date(date_str: str) -> date:
        """Parse date from various formats"""
        if not date_str:
            return None
        date_str = date_str.strip()
        
        # Try ISO format first (YYYY-MM-DD)
        try:
            return date.fromisoformat(date_str)
        except ValueError:
            pass
        
        # Try DD/MM/YYYY or DD/MM/YY
        for fmt in ['%d/%m/%Y', '%d/%m/%y', '%d-%m-%Y', '%d-%m-%y']:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        
        # Try MM/DD/YYYY or MM/DD/YY (US format)
        for fmt in ['%m/%d/%Y', '%m/%d/%y']:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        
        raise ValueError(f"Could not parse date: {date_str}. Please use DD/MM/YYYY format.")
    
    issue_date = None
    expiry_date = None
    if request.issue_date:
        issue_date = parse_date(request.issue_date)
    if request.expiry_date:
        expiry_date = parse_date(request.expiry_date)
    
    # Create the ticket
    new_ticket = UserTicket(
        user_id=current_user.id,
        ticket_type_id=request.ticket_type_id,
        ticket_number=request.ticket_number,
        issue_date=issue_date,
        expiry_date=expiry_date,
        front_image=request.front_image,
        back_image=request.back_image,
        status="pending"
    )
    
    db.add(new_ticket)
    await db.commit()
    await db.refresh(new_ticket)
    
    return {
        "message": "Ticket uploaded successfully",
        "ticket_id": new_ticket.id,
        "status": new_ticket.status
    }


@router.delete("/{ticket_id}")
async def delete_ticket(
    ticket_id: int,
    user_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    """Delete a user's ticket"""
    # Use provided user_id or fall back to first user (temp auth bypass)
    if user_id:
        result = await db.execute(select(User).where(User.id == user_id))
    else:
        result = await db.execute(select(User).limit(1))
    current_user = result.scalar_one_or_none()
    
    if not current_user:
        raise HTTPException(status_code=401, detail="User not found")
    
    # Get the ticket
    result = await db.execute(
        select(UserTicket).where(
            UserTicket.id == ticket_id,
            UserTicket.user_id == current_user.id
        )
    )
    ticket = result.scalar_one_or_none()
    
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    
    await db.delete(ticket)
    await db.commit()
    
    return {"message": "Ticket deleted successfully"}


# ============ ADMIN ENDPOINTS ============

@router.get("/admin/all")
async def get_all_tickets(
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get all user tickets (admin view)"""
    query = select(UserTicket).order_by(UserTicket.created_at.desc())
    
    if status:
        query = query.where(UserTicket.status == status)
    
    result = await db.execute(query)
    tickets = result.scalars().all()
    
    today = date.today()
    ticket_data = []
    
    for ticket in tickets:
        # Get user info
        user_result = await db.execute(
            select(User).where(User.id == ticket.user_id)
        )
        user = user_result.scalar_one_or_none()
        
        # Get ticket type
        type_result = await db.execute(
            select(TicketType).where(TicketType.id == ticket.ticket_type_id)
        )
        ticket_type = type_result.scalar_one_or_none()
        
        is_expired = ticket.expiry_date and ticket.expiry_date < today
        
        ticket_data.append({
            "id": ticket.id,
            "user_id": ticket.user_id,
            "user_name": f"{user.first_name} {user.surname}" if user else "Unknown",
            "user_email": user.email if user else None,
            "ticket_type_id": ticket.ticket_type_id,
            "ticket_type_name": ticket_type.name if ticket_type else "Unknown",
            "ticket_number": ticket.ticket_number,
            "issue_date": ticket.issue_date.isoformat() if ticket.issue_date else None,
            "expiry_date": ticket.expiry_date.isoformat() if ticket.expiry_date else None,
            "front_image": ticket.front_image,
            "back_image": ticket.back_image,
            "status": ticket.status,
            "is_expired": is_expired,
            "created_at": ticket.created_at.isoformat()
        })
    
    return {"tickets": ticket_data}


@router.post("/admin/{ticket_id}/verify")
async def verify_ticket(
    ticket_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Verify a user's ticket (admin)"""
    result = await db.execute(
        select(UserTicket).where(UserTicket.id == ticket_id)
    )
    ticket = result.scalar_one_or_none()
    
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    
    ticket.status = "verified"
    ticket.verified_at = datetime.utcnow()
    await db.commit()
    
    return {"message": "Ticket verified", "ticket_id": ticket_id}


@router.post("/admin/{ticket_id}/reject")
async def reject_ticket(
    ticket_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Reject a user's ticket (admin)"""
    result = await db.execute(
        select(UserTicket).where(UserTicket.id == ticket_id)
    )
    ticket = result.scalar_one_or_none()
    
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    
    ticket.status = "rejected"
    await db.commit()
    
    return {"message": "Ticket rejected", "ticket_id": ticket_id}
