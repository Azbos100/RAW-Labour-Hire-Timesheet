"""
MYOB Business Integration Routes
Handles OAuth2 authentication and timesheet/invoice exports
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
import httpx
import os
import json
import csv
import io

from ..database import get_db
from ..models import (
    MYOBSettings, MYOBExport, TimesheetEntry, Timesheet,
    User, Client, JobSite
)

router = APIRouter()

# MYOB OAuth2 endpoints
MYOB_AUTH_URL = "https://secure.myob.com/oauth2/account/authorize"
MYOB_TOKEN_URL = "https://secure.myob.com/oauth2/v1/authorize"
MYOB_API_URL = "https://api.myob.com/accountright"

# Redirect URI (update this to your domain)
REDIRECT_URI = os.getenv("MYOB_REDIRECT_URI", "http://localhost:8000/api/myob/callback")


class MYOBCredentials(BaseModel):
    client_id: str
    client_secret: str


class MYOBStatus(BaseModel):
    is_connected: bool
    company_file_name: Optional[str] = None
    last_sync_at: Optional[datetime] = None
    has_credentials: bool = False


class ExportRequest(BaseModel):
    entry_ids: List[int]
    export_invoices: bool = True
    export_payroll: bool = True


class WorkerPayRates(BaseModel):
    base_pay_rate: float = 0
    overtime_pay_rate: float = 0
    weekend_pay_rate: float = 0
    night_pay_rate: float = 0


class ClientBillingRates(BaseModel):
    hourly_billing_rate: float = 0
    overtime_billing_rate: float = 0
    weekend_billing_rate: float = 0
    night_billing_rate: float = 0


# ==================== CONNECTION STATUS ====================

@router.get("/status")
async def get_myob_status(db: AsyncSession = Depends(get_db)):
    """Get current MYOB connection status"""
    result = await db.execute(select(MYOBSettings).limit(1))
    settings = result.scalar_one_or_none()
    
    if not settings:
        return MYOBStatus(
            is_connected=False,
            has_credentials=False
        )
    
    return MYOBStatus(
        is_connected=settings.is_connected,
        company_file_name=settings.company_file_name,
        last_sync_at=settings.last_sync_at,
        has_credentials=bool(settings.client_id and settings.client_secret)
    )


# ==================== CREDENTIALS SETUP ====================

@router.post("/credentials")
async def save_credentials(
    credentials: MYOBCredentials,
    db: AsyncSession = Depends(get_db)
):
    """Save MYOB API credentials"""
    result = await db.execute(select(MYOBSettings).limit(1))
    settings = result.scalar_one_or_none()
    
    if not settings:
        settings = MYOBSettings()
        db.add(settings)
    
    settings.client_id = credentials.client_id
    settings.client_secret = credentials.client_secret
    settings.updated_at = datetime.utcnow()
    
    await db.commit()
    
    return {"message": "Credentials saved successfully"}


# ==================== OAUTH2 FLOW ====================

@router.get("/auth-url")
async def get_auth_url(db: AsyncSession = Depends(get_db)):
    """Get MYOB OAuth2 authorization URL"""
    result = await db.execute(select(MYOBSettings).limit(1))
    settings = result.scalar_one_or_none()
    
    if not settings or not settings.client_id:
        raise HTTPException(status_code=400, detail="MYOB credentials not configured")
    
    auth_url = (
        f"{MYOB_AUTH_URL}"
        f"?client_id={settings.client_id}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=CompanyFile"
    )
    
    return {"auth_url": auth_url}


@router.get("/callback")
async def oauth_callback(
    code: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Handle OAuth2 callback from MYOB"""
    result = await db.execute(select(MYOBSettings).limit(1))
    settings = result.scalar_one_or_none()
    
    if not settings:
        raise HTTPException(status_code=400, detail="MYOB not configured")
    
    # Exchange code for tokens
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            MYOB_TOKEN_URL,
            data={
                "client_id": settings.client_id,
                "client_secret": settings.client_secret,
                "code": code,
                "redirect_uri": REDIRECT_URI,
                "grant_type": "authorization_code",
                "scope": "CompanyFile"
            }
        )
        
        if token_response.status_code != 200:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to get tokens: {token_response.text}"
            )
        
        tokens = token_response.json()
    
    # Save tokens
    settings.access_token = tokens.get("access_token")
    settings.refresh_token = tokens.get("refresh_token")
    expires_in = tokens.get("expires_in", 1200)  # Default 20 minutes
    settings.token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
    settings.is_connected = True
    settings.updated_at = datetime.utcnow()
    
    await db.commit()
    
    # Redirect to admin dashboard
    return RedirectResponse(url="/admin?myob=connected")


@router.post("/refresh-token")
async def refresh_token(db: AsyncSession = Depends(get_db)):
    """Refresh MYOB access token"""
    result = await db.execute(select(MYOBSettings).limit(1))
    settings = result.scalar_one_or_none()
    
    if not settings or not settings.refresh_token:
        raise HTTPException(status_code=400, detail="No refresh token available")
    
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            MYOB_TOKEN_URL,
            data={
                "client_id": settings.client_id,
                "client_secret": settings.client_secret,
                "refresh_token": settings.refresh_token,
                "grant_type": "refresh_token"
            }
        )
        
        if token_response.status_code != 200:
            settings.is_connected = False
            await db.commit()
            raise HTTPException(status_code=400, detail="Failed to refresh token")
        
        tokens = token_response.json()
    
    settings.access_token = tokens.get("access_token")
    if tokens.get("refresh_token"):
        settings.refresh_token = tokens.get("refresh_token")
    expires_in = tokens.get("expires_in", 1200)
    settings.token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
    settings.updated_at = datetime.utcnow()
    
    await db.commit()
    
    return {"message": "Token refreshed successfully"}


@router.post("/disconnect")
async def disconnect_myob(db: AsyncSession = Depends(get_db)):
    """Disconnect from MYOB"""
    result = await db.execute(select(MYOBSettings).limit(1))
    settings = result.scalar_one_or_none()
    
    if settings:
        settings.access_token = None
        settings.refresh_token = None
        settings.is_connected = False
        settings.company_file_id = None
        settings.company_file_name = None
        await db.commit()
    
    return {"message": "Disconnected from MYOB"}


# ==================== COMPANY FILES ====================

@router.get("/company-files")
async def get_company_files(db: AsyncSession = Depends(get_db)):
    """Get available MYOB company files"""
    settings = await _get_valid_settings(db)
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            MYOB_API_URL,
            headers={
                "Authorization": f"Bearer {settings.access_token}",
                "x-myobapi-key": settings.client_id,
                "x-myobapi-version": "v2"
            }
        )
        
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to get company files")
        
        return response.json()


@router.post("/select-company-file")
async def select_company_file(
    file_id: str,
    file_name: str,
    file_uri: str,
    db: AsyncSession = Depends(get_db)
):
    """Select a company file to use"""
    result = await db.execute(select(MYOBSettings).limit(1))
    settings = result.scalar_one_or_none()
    
    if not settings:
        raise HTTPException(status_code=400, detail="MYOB not configured")
    
    settings.company_file_id = file_id
    settings.company_file_name = file_name
    settings.company_file_uri = file_uri
    
    await db.commit()
    
    return {"message": f"Selected company file: {file_name}"}


# ==================== WORKER PAY RATES ====================

@router.get("/workers")
async def get_workers_with_rates(db: AsyncSession = Depends(get_db)):
    """Get all workers with their pay rates"""
    result = await db.execute(
        select(User).where(User.is_active == True)
    )
    workers = result.scalars().all()
    
    return {
        "workers": [
            {
                "id": w.id,
                "name": f"{w.first_name} {w.surname}",
                "email": w.email,
                "base_pay_rate": w.base_pay_rate or 0,
                "overtime_pay_rate": w.overtime_pay_rate or 0,
                "weekend_pay_rate": w.weekend_pay_rate or 0,
                "night_pay_rate": w.night_pay_rate or 0,
                "myob_employee_id": w.myob_employee_id
            }
            for w in workers
        ]
    }


@router.put("/workers/{worker_id}/rates")
async def update_worker_rates(
    worker_id: int,
    rates: WorkerPayRates,
    db: AsyncSession = Depends(get_db)
):
    """Update worker pay rates"""
    result = await db.execute(select(User).where(User.id == worker_id))
    worker = result.scalar_one_or_none()
    
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    
    worker.base_pay_rate = rates.base_pay_rate
    worker.overtime_pay_rate = rates.overtime_pay_rate
    worker.weekend_pay_rate = rates.weekend_pay_rate
    worker.night_pay_rate = rates.night_pay_rate
    
    await db.commit()
    
    return {"message": "Pay rates updated"}


@router.put("/workers/{worker_id}/myob-id")
async def update_worker_myob_id(
    worker_id: int,
    myob_employee_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Link worker to MYOB employee"""
    result = await db.execute(select(User).where(User.id == worker_id))
    worker = result.scalar_one_or_none()
    
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    
    worker.myob_employee_id = myob_employee_id
    await db.commit()
    
    return {"message": "MYOB Employee ID updated"}


# ==================== CLIENT BILLING RATES ====================

@router.get("/clients")
async def get_clients_with_rates(db: AsyncSession = Depends(get_db)):
    """Get all clients with their billing rates"""
    result = await db.execute(
        select(Client).where(Client.is_active == True)
    )
    clients = result.scalars().all()
    
    return {
        "clients": [
            {
                "id": c.id,
                "name": c.name,
                "hourly_billing_rate": c.hourly_billing_rate or 0,
                "overtime_billing_rate": c.overtime_billing_rate or 0,
                "weekend_billing_rate": c.weekend_billing_rate or 0,
                "night_billing_rate": c.night_billing_rate or 0,
                "myob_customer_id": c.myob_customer_id
            }
            for c in clients
        ]
    }


@router.put("/clients/{client_id}/rates")
async def update_client_rates(
    client_id: int,
    rates: ClientBillingRates,
    db: AsyncSession = Depends(get_db)
):
    """Update client billing rates"""
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    client.hourly_billing_rate = rates.hourly_billing_rate
    client.overtime_billing_rate = rates.overtime_billing_rate
    client.weekend_billing_rate = rates.weekend_billing_rate
    client.night_billing_rate = rates.night_billing_rate
    
    await db.commit()
    
    return {"message": "Billing rates updated"}


@router.put("/clients/{client_id}/myob-id")
async def update_client_myob_id(
    client_id: int,
    myob_customer_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Link client to MYOB customer"""
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    client.myob_customer_id = myob_customer_id
    await db.commit()
    
    return {"message": "MYOB Customer ID updated"}


# ==================== EXPORT TO MYOB ====================

@router.get("/approved-entries")
async def get_approved_entries_for_export(db: AsyncSession = Depends(get_db)):
    """Get approved timesheet entries ready for export"""
    result = await db.execute(
        select(TimesheetEntry)
        .join(Timesheet)
        .join(User, User.id == Timesheet.worker_id)
        .join(Client, Client.id == Timesheet.client_id)
        .where(TimesheetEntry.entry_status == "approved")
        .order_by(TimesheetEntry.entry_date.desc())
    )
    entries = result.scalars().all()
    
    # Get export history
    exported_entry_ids = set()
    export_result = await db.execute(
        select(MYOBExport.entry_id).where(
            and_(
                MYOBExport.entry_id.isnot(None),
                MYOBExport.export_status == "success"
            )
        )
    )
    exported_entry_ids = {r[0] for r in export_result.fetchall()}
    
    entries_data = []
    for entry in entries:
        # Get related data
        ts_result = await db.execute(
            select(Timesheet).where(Timesheet.id == entry.timesheet_id)
        )
        timesheet = ts_result.scalar_one()
        
        worker_result = await db.execute(
            select(User).where(User.id == timesheet.worker_id)
        )
        worker = worker_result.scalar_one()
        
        client_result = await db.execute(
            select(Client).where(Client.id == timesheet.client_id)
        )
        client = client_result.scalar_one()
        
        entries_data.append({
            "id": entry.id,
            "date": entry.entry_date.isoformat() if entry.entry_date else None,
            "day_of_week": entry.day_of_week,
            "worker_id": worker.id,
            "worker_name": f"{worker.first_name} {worker.surname}",
            "client_id": client.id,
            "client_name": client.name,
            "hours": entry.total_hours or 0,
            "ordinary_hours": entry.ordinary_hours or 0,
            "overtime_hours": entry.overtime_hours or 0,
            "job_site": entry.job_site.name if entry.job_site else "General",
            "already_exported": entry.id in exported_entry_ids
        })
    
    return {"entries": entries_data}


@router.post("/export")
async def export_to_myob(
    request: ExportRequest,
    db: AsyncSession = Depends(get_db)
):
    """Export selected entries to MYOB"""
    settings = await _get_valid_settings(db)
    
    if not settings.company_file_id:
        raise HTTPException(status_code=400, detail="No company file selected")
    
    results = {
        "invoices_created": 0,
        "payroll_entries": 0,
        "errors": []
    }
    
    for entry_id in request.entry_ids:
        try:
            # Get entry with related data
            entry_result = await db.execute(
                select(TimesheetEntry).where(TimesheetEntry.id == entry_id)
            )
            entry = entry_result.scalar_one_or_none()
            
            if not entry:
                results["errors"].append(f"Entry {entry_id} not found")
                continue
            
            ts_result = await db.execute(
                select(Timesheet).where(Timesheet.id == entry.timesheet_id)
            )
            timesheet = ts_result.scalar_one()
            
            worker_result = await db.execute(
                select(User).where(User.id == timesheet.worker_id)
            )
            worker = worker_result.scalar_one()
            
            client_result = await db.execute(
                select(Client).where(Client.id == timesheet.client_id)
            )
            client = client_result.scalar_one()
            
            # Create invoice if requested
            if request.export_invoices and client.myob_customer_id:
                invoice_result = await _create_myob_invoice(
                    settings, entry, worker, client, db
                )
                if invoice_result.get("success"):
                    results["invoices_created"] += 1
                else:
                    results["errors"].append(invoice_result.get("error"))
            
            # Create payroll entry if requested
            if request.export_payroll and worker.myob_employee_id:
                payroll_result = await _create_myob_timesheet(
                    settings, entry, worker, db
                )
                if payroll_result.get("success"):
                    results["payroll_entries"] += 1
                else:
                    results["errors"].append(payroll_result.get("error"))
            
        except Exception as e:
            results["errors"].append(f"Entry {entry_id}: {str(e)}")
    
    return results


@router.get("/export-history")
async def get_export_history(db: AsyncSession = Depends(get_db)):
    """Get MYOB export history"""
    result = await db.execute(
        select(MYOBExport).order_by(MYOBExport.exported_at.desc()).limit(100)
    )
    exports = result.scalars().all()
    
    return {
        "exports": [
            {
                "id": e.id,
                "entry_id": e.entry_id,
                "export_type": e.export_type,
                "exported_at": e.exported_at.isoformat() if e.exported_at else None,
                "status": e.export_status,
                "invoice_amount": e.invoice_amount,
                "pay_amount": e.pay_amount,
                "error": e.error_message
            }
            for e in exports
        ]
    }


# ==================== HELPER FUNCTIONS ====================

async def _get_valid_settings(db: AsyncSession) -> MYOBSettings:
    """Get MYOB settings and refresh token if needed"""
    result = await db.execute(select(MYOBSettings).limit(1))
    settings = result.scalar_one_or_none()
    
    if not settings or not settings.is_connected:
        raise HTTPException(status_code=400, detail="MYOB not connected")
    
    # Check if token needs refresh
    if settings.token_expires_at and settings.token_expires_at < datetime.utcnow():
        await refresh_token(db)
        # Re-fetch settings after refresh
        result = await db.execute(select(MYOBSettings).limit(1))
        settings = result.scalar_one_or_none()
    
    return settings


async def _create_myob_invoice(
    settings: MYOBSettings,
    entry: TimesheetEntry,
    worker: User,
    client: Client,
    db: AsyncSession
) -> dict:
    """Create an invoice in MYOB for the timesheet entry"""
    try:
        # Calculate amounts
        hours = entry.total_hours or 0
        ordinary = entry.ordinary_hours or 0
        overtime = entry.overtime_hours or 0
        
        # Use client billing rates
        amount = (ordinary * (client.hourly_billing_rate or 0)) + \
                 (overtime * (client.overtime_billing_rate or 0))
        
        # Build invoice payload for MYOB
        invoice_data = {
            "Customer": {"UID": client.myob_customer_id},
            "Date": entry.entry_date.isoformat() if entry.entry_date else datetime.utcnow().date().isoformat(),
            "Lines": [
                {
                    "Type": "Transaction",
                    "Description": f"Labour Hire - {worker.first_name} {worker.surname} - {entry.entry_date}",
                    "Total": amount,
                    "TaxCode": {"Code": "GST"}
                }
            ]
        }
        
        async with httpx.AsyncClient() as http_client:
            response = await http_client.post(
                f"{settings.company_file_uri}/Sale/Invoice/Service",
                headers={
                    "Authorization": f"Bearer {settings.access_token}",
                    "x-myobapi-key": settings.client_id,
                    "x-myobapi-version": "v2",
                    "Content-Type": "application/json"
                },
                json=invoice_data
            )
            
            if response.status_code in [200, 201]:
                # Record successful export
                export = MYOBExport(
                    entry_id=entry.id,
                    export_type="invoice",
                    myob_invoice_id=response.headers.get("Location", ""),
                    export_status="success",
                    invoice_amount=amount,
                    invoice_date=entry.entry_date
                )
                db.add(export)
                await db.commit()
                return {"success": True}
            else:
                # Record failed export
                export = MYOBExport(
                    entry_id=entry.id,
                    export_type="invoice",
                    export_status="failed",
                    error_message=response.text
                )
                db.add(export)
                await db.commit()
                return {"success": False, "error": response.text}
                
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _create_myob_timesheet(
    settings: MYOBSettings,
    entry: TimesheetEntry,
    worker: User,
    db: AsyncSession
) -> dict:
    """Create a timesheet entry in MYOB for payroll"""
    try:
        # Calculate pay amount
        hours = entry.total_hours or 0
        ordinary = entry.ordinary_hours or 0
        overtime = entry.overtime_hours or 0
        
        pay_amount = (ordinary * (worker.base_pay_rate or 0)) + \
                     (overtime * (worker.overtime_pay_rate or 0))
        
        # Build timesheet payload for MYOB
        # Note: MYOB timesheet structure varies, this is a common format
        timesheet_data = {
            "Employee": {"UID": worker.myob_employee_id},
            "StartDate": entry.entry_date.isoformat() if entry.entry_date else None,
            "EndDate": entry.entry_date.isoformat() if entry.entry_date else None,
            "Lines": [
                {
                    "PayrollCategory": {"Name": "Base Hourly"},
                    "Hours": ordinary
                }
            ]
        }
        
        if overtime > 0:
            timesheet_data["Lines"].append({
                "PayrollCategory": {"Name": "Overtime"},
                "Hours": overtime
            })
        
        async with httpx.AsyncClient() as http_client:
            response = await http_client.post(
                f"{settings.company_file_uri}/Payroll/Timesheet",
                headers={
                    "Authorization": f"Bearer {settings.access_token}",
                    "x-myobapi-key": settings.client_id,
                    "x-myobapi-version": "v2",
                    "Content-Type": "application/json"
                },
                json=timesheet_data
            )
            
            if response.status_code in [200, 201]:
                export = MYOBExport(
                    entry_id=entry.id,
                    export_type="payroll",
                    myob_timesheet_id=response.headers.get("Location", ""),
                    export_status="success",
                    pay_amount=pay_amount,
                    hours_exported=hours
                )
                db.add(export)
                await db.commit()
                return {"success": True}
            else:
                export = MYOBExport(
                    entry_id=entry.id,
                    export_type="payroll",
                    export_status="failed",
                    error_message=response.text
                )
                db.add(export)
                await db.commit()
                return {"success": False, "error": response.text}
                
    except Exception as e:
        return {"success": False, "error": str(e)}


# ==================== CSV EXPORT ====================

@router.get("/export-csv/invoices")
async def export_invoices_csv(db: AsyncSession = Depends(get_db)):
    """Export approved entries as CSV for MYOB invoice import"""
    result = await db.execute(
        select(TimesheetEntry)
        .where(TimesheetEntry.entry_status == "approved")
        .order_by(TimesheetEntry.entry_date.desc())
    )
    entries = result.scalars().all()
    
    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    
    # MYOB Invoice Import headers
    writer.writerow([
        'Customer Name',
        'Invoice Number',
        'Invoice Date',
        'Description',
        'Quantity',
        'Unit Price',
        'Total (Inc Tax)',
        'Tax Code',
        'Job Site',
        'Worker Name'
    ])
    
    invoice_num = 1000
    for entry in entries:
        # Get related data
        ts_result = await db.execute(
            select(Timesheet).where(Timesheet.id == entry.timesheet_id)
        )
        timesheet = ts_result.scalar_one_or_none()
        if not timesheet:
            continue
            
        worker_result = await db.execute(
            select(User).where(User.id == timesheet.worker_id)
        )
        worker = worker_result.scalar_one_or_none()
        
        client_result = await db.execute(
            select(Client).where(Client.id == timesheet.client_id)
        )
        client = client_result.scalar_one_or_none()
        
        if not worker or not client:
            continue
        
        hours = entry.total_hours or 0
        rate = client.hourly_billing_rate or 0
        total = hours * rate
        
        job_site_name = entry.job_site.name if entry.job_site else "General"
        worker_name = f"{worker.first_name} {worker.surname}"
        
        writer.writerow([
            client.name,
            f"INV-{invoice_num}",
            entry.entry_date.strftime('%d/%m/%Y') if entry.entry_date else '',
            f"Labour Hire - {worker_name} - {entry.entry_date}",
            hours,
            rate,
            total * 1.1,  # Include 10% GST
            'GST',
            job_site_name,
            worker_name
        ])
        invoice_num += 1
    
    output.seek(0)
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=invoices_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
        }
    )


@router.get("/export-csv/payroll")
async def export_payroll_csv(db: AsyncSession = Depends(get_db)):
    """Export approved entries as CSV for MYOB payroll import"""
    result = await db.execute(
        select(TimesheetEntry)
        .where(TimesheetEntry.entry_status == "approved")
        .order_by(TimesheetEntry.entry_date.desc())
    )
    entries = result.scalars().all()
    
    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    
    # MYOB Payroll/Timesheet Import headers
    writer.writerow([
        'Employee First Name',
        'Employee Last Name',
        'Employee Email',
        'Date',
        'Day',
        'Start Time',
        'End Time',
        'Ordinary Hours',
        'Overtime Hours',
        'Total Hours',
        'Base Pay Rate',
        'Overtime Pay Rate',
        'Total Pay',
        'Job Site',
        'Client'
    ])
    
    for entry in entries:
        # Get related data
        ts_result = await db.execute(
            select(Timesheet).where(Timesheet.id == entry.timesheet_id)
        )
        timesheet = ts_result.scalar_one_or_none()
        if not timesheet:
            continue
            
        worker_result = await db.execute(
            select(User).where(User.id == timesheet.worker_id)
        )
        worker = worker_result.scalar_one_or_none()
        
        client_result = await db.execute(
            select(Client).where(Client.id == timesheet.client_id)
        )
        client = client_result.scalar_one_or_none()
        
        if not worker or not client:
            continue
        
        ordinary = entry.ordinary_hours or 0
        overtime = entry.overtime_hours or 0
        total_hours = entry.total_hours or 0
        
        base_rate = worker.base_pay_rate or 0
        ot_rate = worker.overtime_pay_rate or 0
        total_pay = (ordinary * base_rate) + (overtime * ot_rate)
        
        job_site_name = entry.job_site.name if entry.job_site else "General"
        
        # Format times
        start_time = entry.time_start.strftime('%H:%M') if entry.time_start else ''
        end_time = entry.time_finish.strftime('%H:%M') if entry.time_finish else ''
        
        writer.writerow([
            worker.first_name,
            worker.surname,
            worker.email,
            entry.entry_date.strftime('%d/%m/%Y') if entry.entry_date else '',
            entry.day_of_week or '',
            start_time,
            end_time,
            ordinary,
            overtime,
            total_hours,
            base_rate,
            ot_rate,
            total_pay,
            job_site_name,
            client.name
        ])
    
    output.seek(0)
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=payroll_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
        }
    )


@router.get("/export-csv/timesheets")
async def export_timesheets_csv(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Export all approved timesheet data as comprehensive CSV"""
    query = select(TimesheetEntry).where(TimesheetEntry.entry_status == "approved")
    
    # Apply date filters if provided
    if start_date:
        from datetime import datetime as dt
        start = dt.strptime(start_date, '%Y-%m-%d').date()
        query = query.where(TimesheetEntry.entry_date >= start)
    if end_date:
        from datetime import datetime as dt
        end = dt.strptime(end_date, '%Y-%m-%d').date()
        query = query.where(TimesheetEntry.entry_date <= end)
    
    result = await db.execute(query.order_by(TimesheetEntry.entry_date.desc()))
    entries = result.scalars().all()
    
    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Comprehensive headers
    writer.writerow([
        'Date',
        'Day',
        'Worker First Name',
        'Worker Last Name',
        'Worker Email',
        'Client',
        'Job Site',
        'Site Address',
        'Start Time',
        'End Time',
        'Ordinary Hours',
        'Overtime Hours',
        'Total Hours',
        'Worker Base Rate',
        'Worker OT Rate',
        'Worker Pay',
        'Client Hourly Rate',
        'Client OT Rate',
        'Invoice Amount',
        'Supervisor Name',
        'Supervisor Contact',
        'Clock In Time',
        'Clock In Location',
        'Clock Out Time',
        'Clock Out Location',
        'Status'
    ])
    
    for entry in entries:
        # Get related data
        ts_result = await db.execute(
            select(Timesheet).where(Timesheet.id == entry.timesheet_id)
        )
        timesheet = ts_result.scalar_one_or_none()
        if not timesheet:
            continue
            
        worker_result = await db.execute(
            select(User).where(User.id == timesheet.worker_id)
        )
        worker = worker_result.scalar_one_or_none()
        
        client_result = await db.execute(
            select(Client).where(Client.id == timesheet.client_id)
        )
        client = client_result.scalar_one_or_none()
        
        if not worker or not client:
            continue
        
        ordinary = entry.ordinary_hours or 0
        overtime = entry.overtime_hours or 0
        total_hours = entry.total_hours or 0
        
        # Worker pay calculation
        base_rate = worker.base_pay_rate or 0
        ot_rate = worker.overtime_pay_rate or 0
        worker_pay = (ordinary * base_rate) + (overtime * ot_rate)
        
        # Client billing calculation
        client_rate = client.hourly_billing_rate or 0
        client_ot_rate = client.overtime_billing_rate or 0
        invoice_amount = ((ordinary * client_rate) + (overtime * client_ot_rate)) * 1.1  # Inc GST
        
        job_site_name = entry.job_site.name if entry.job_site else "General"
        job_site_address = entry.job_site.address if entry.job_site else ""
        
        # Format times
        start_time = entry.time_start.strftime('%H:%M') if entry.time_start else ''
        end_time = entry.time_finish.strftime('%H:%M') if entry.time_finish else ''
        
        clock_in = entry.clock_in_time.strftime('%Y-%m-%d %H:%M') if entry.clock_in_time else ''
        clock_out = entry.clock_out_time.strftime('%Y-%m-%d %H:%M') if entry.clock_out_time else ''
        
        writer.writerow([
            entry.entry_date.strftime('%d/%m/%Y') if entry.entry_date else '',
            entry.day_of_week or '',
            worker.first_name,
            worker.surname,
            worker.email,
            client.name,
            job_site_name,
            job_site_address,
            start_time,
            end_time,
            ordinary,
            overtime,
            total_hours,
            base_rate,
            ot_rate,
            round(worker_pay, 2),
            client_rate,
            client_ot_rate,
            round(invoice_amount, 2),
            entry.supervisor_name or '',
            entry.supervisor_contact or '',
            clock_in,
            entry.clock_in_address or '',
            clock_out,
            entry.clock_out_address or '',
            entry.entry_status or ''
        ])
    
    output.seek(0)
    
    filename = f"timesheets_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )
