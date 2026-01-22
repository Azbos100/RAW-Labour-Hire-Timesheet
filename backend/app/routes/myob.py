"""
RAW Labour Hire - MYOB Integration API
Export timesheets to MYOB for client billing
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from datetime import datetime, date
from typing import Optional, List
import httpx

from ..database import get_db
from ..models import User, Timesheet, Client, MYOBExport, TimesheetStatus, UserRole
from .auth import get_current_user

router = APIRouter()

# MYOB API Configuration (will need to be set up with MYOB developer account)
MYOB_API_BASE = "https://api.myob.com/accountright"
MYOB_CLIENT_ID = "your-myob-client-id"  # TODO: Move to env
MYOB_CLIENT_SECRET = "your-myob-client-secret"  # TODO: Move to env


class MYOBExportRequest(BaseModel):
    timesheet_ids: List[int]


class MYOBConnectionStatus(BaseModel):
    connected: bool
    company_name: Optional[str] = None
    last_sync: Optional[datetime] = None


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Require admin role for MYOB operations"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


@router.get("/status")
async def get_myob_status(
    current_user: User = Depends(require_admin)
):
    """Check MYOB connection status"""
    # TODO: Implement actual MYOB connection check
    return MYOBConnectionStatus(
        connected=False,
        company_name=None,
        last_sync=None
    )


@router.post("/connect")
async def connect_myob(
    current_user: User = Depends(require_admin)
):
    """
    Initiate MYOB OAuth connection.
    Returns URL to redirect user to for MYOB authorization.
    """
    # TODO: Implement MYOB OAuth flow
    # This would typically:
    # 1. Generate OAuth state
    # 2. Return MYOB authorization URL
    # 3. Handle callback with authorization code
    # 4. Exchange code for access/refresh tokens
    
    return {
        "message": "MYOB integration coming soon",
        "setup_required": True,
        "instructions": [
            "1. Register for MYOB Developer account",
            "2. Create an app to get Client ID and Secret",
            "3. Configure OAuth callback URL",
            "4. Update environment variables"
        ]
    }


@router.get("/export-preview")
async def preview_export(
    week_starting: date,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Preview timesheets ready for MYOB export.
    Shows approved timesheets grouped by client for the specified week.
    """
    result = await db.execute(
        select(Timesheet, Client)
        .join(Client)
        .where(
            Timesheet.week_starting == week_starting,
            Timesheet.status == TimesheetStatus.APPROVED
        )
        .order_by(Client.name)
    )
    rows = result.all()
    
    # Group by client
    clients_data = {}
    for timesheet, client in rows:
        if client.id not in clients_data:
            clients_data[client.id] = {
                "client_id": client.id,
                "client_name": client.name,
                "myob_customer_id": client.myob_customer_id,
                "hourly_rate": client.default_hourly_rate,
                "overtime_rate": client.default_overtime_rate,
                "timesheets": [],
                "total_ordinary_hours": 0,
                "total_overtime_hours": 0,
                "total_hours": 0,
                "estimated_invoice": 0
            }
        
        clients_data[client.id]["timesheets"].append({
            "id": timesheet.id,
            "docket_number": timesheet.docket_number,
            "worker_id": timesheet.worker_id,
            "ordinary_hours": timesheet.total_ordinary_hours,
            "overtime_hours": timesheet.total_overtime_hours,
            "total_hours": timesheet.total_hours
        })
        clients_data[client.id]["total_ordinary_hours"] += timesheet.total_ordinary_hours
        clients_data[client.id]["total_overtime_hours"] += timesheet.total_overtime_hours
        clients_data[client.id]["total_hours"] += timesheet.total_hours
    
    # Calculate estimated invoice amounts
    for client_id, data in clients_data.items():
        data["estimated_invoice"] = (
            data["total_ordinary_hours"] * data["hourly_rate"] +
            data["total_overtime_hours"] * data["overtime_rate"]
        )
    
    return {
        "week_starting": week_starting.isoformat(),
        "clients": list(clients_data.values()),
        "total_timesheets": len(rows),
        "ready_for_export": all(c.get("myob_customer_id") for c in clients_data.values())
    }


@router.post("/export")
async def export_to_myob(
    request: MYOBExportRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Export approved timesheets to MYOB as invoices.
    Creates invoices in MYOB for each client.
    """
    # Get timesheets
    result = await db.execute(
        select(Timesheet)
        .where(
            Timesheet.id.in_(request.timesheet_ids),
            Timesheet.status == TimesheetStatus.APPROVED
        )
    )
    timesheets = result.scalars().all()
    
    if not timesheets:
        raise HTTPException(status_code=400, detail="No approved timesheets found")
    
    # TODO: Implement actual MYOB API calls
    # For now, just record the export attempt
    
    exports = []
    for ts in timesheets:
        export = MYOBExport(
            timesheet_id=ts.id,
            export_status="pending",
            invoice_date=date.today()
        )
        db.add(export)
        exports.append({
            "timesheet_id": ts.id,
            "docket_number": ts.docket_number,
            "status": "pending"
        })
    
    await db.commit()
    
    return {
        "message": f"Export initiated for {len(timesheets)} timesheets",
        "exports": exports,
        "note": "MYOB integration pending setup"
    }


@router.get("/export-history")
async def get_export_history(
    limit: int = 50,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get history of MYOB exports"""
    result = await db.execute(
        select(MYOBExport)
        .order_by(MYOBExport.exported_at.desc())
        .limit(limit)
    )
    exports = result.scalars().all()
    
    return {
        "exports": [
            {
                "id": e.id,
                "timesheet_id": e.timesheet_id,
                "exported_at": e.exported_at.isoformat(),
                "status": e.export_status,
                "myob_invoice_id": e.myob_invoice_id,
                "invoice_amount": e.invoice_amount,
                "error": e.error_message
            }
            for e in exports
        ]
    }
