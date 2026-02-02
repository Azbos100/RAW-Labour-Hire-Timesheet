"""
RAW Labour Hire - Induction/SWMS API
"""

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List
import os
import uuid

from ..database import get_db
from ..models import User, InductionDocument, UserInduction

router = APIRouter()

# PDF storage directory
PDF_STORAGE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads", "pdfs")
os.makedirs(PDF_STORAGE_DIR, exist_ok=True)


# ============ PYDANTIC MODELS ============

class DocumentResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    content: str
    document_type: str
    category: Optional[str]
    version: str
    is_required: bool


class UserInductionStatus(BaseModel):
    document_id: int
    document_title: str
    document_type: str
    category: Optional[str]
    is_required: bool
    status: str  # pending, signed
    signed_at: Optional[str]


class SignDocumentRequest(BaseModel):
    document_id: int
    signature: str  # Base64 encoded


class InductionProgressResponse(BaseModel):
    total_required: int
    total_signed: int
    is_complete: bool
    documents: List[UserInductionStatus]


# ============ USER ENDPOINTS ============

@router.get("/documents")
async def get_induction_documents(
    db: AsyncSession = Depends(get_db)
):
    """Get all active induction documents"""
    result = await db.execute(
        select(InductionDocument)
        .where(InductionDocument.is_active == True)
        .order_by(InductionDocument.display_order, InductionDocument.title)
    )
    documents = result.scalars().all()
    
    return {
        "documents": [
            {
                "id": doc.id,
                "title": doc.title,
                "description": doc.description,
                "content": doc.content,
                "document_type": doc.document_type,
                "category": doc.category,
                "version": doc.version,
                "is_required": doc.is_required,
                "pdf_filename": doc.pdf_filename,
                "pdf_url": f"/api/induction/pdf/{doc.pdf_filename}" if doc.pdf_filename else None,
            }
            for doc in documents
        ]
    }


@router.get("/pdf/{filename}")
async def get_pdf_file(filename: str):
    """Serve a PDF file"""
    file_path = os.path.join(PDF_STORAGE_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="PDF not found")
    return FileResponse(file_path, media_type="application/pdf", filename=filename)


@router.get("/status")
async def get_induction_status(
    user_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get user's induction progress"""
    # Use provided user_id or fall back to first user (temp auth bypass)
    if user_id:
        result = await db.execute(select(User).where(User.id == user_id))
    else:
        result = await db.execute(select(User).limit(1))
    current_user = result.scalar_one_or_none()
    
    if not current_user:
        return {
            "total_required": 0,
            "total_signed": 0,
            "is_complete": True,
            "documents": []
        }
    
    # Get all active documents
    docs_result = await db.execute(
        select(InductionDocument)
        .where(InductionDocument.is_active == True)
        .order_by(InductionDocument.display_order, InductionDocument.title)
    )
    documents = docs_result.scalars().all()
    
    # Get user's signed documents
    signed_result = await db.execute(
        select(UserInduction)
        .where(UserInduction.user_id == current_user.id, UserInduction.status == "signed")
    )
    signed_inductions = {ui.document_id: ui for ui in signed_result.scalars().all()}
    
    # Build status list
    doc_statuses = []
    total_required = 0
    total_signed = 0
    
    for doc in documents:
        if doc.is_required:
            total_required += 1
        
        signed = signed_inductions.get(doc.id)
        if signed:
            total_signed += 1 if doc.is_required else 0
            status = "signed"
            signed_at = signed.signed_at.isoformat() if signed.signed_at else None
        else:
            status = "pending"
            signed_at = None
        
        doc_statuses.append({
            "document_id": doc.id,
            "document_title": doc.title,
            "document_type": doc.document_type,
            "category": doc.category,
            "is_required": doc.is_required,
            "status": status,
            "signed_at": signed_at,
        })
    
    return {
        "total_required": total_required,
        "total_signed": total_signed,
        "is_complete": total_signed >= total_required,
        "documents": doc_statuses
    }


@router.post("/sign")
async def sign_document(
    request: SignDocumentRequest,
    user_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    """Sign an induction document"""
    # Use provided user_id or fall back to first user (temp auth bypass)
    if user_id:
        result = await db.execute(select(User).where(User.id == user_id))
    else:
        result = await db.execute(select(User).limit(1))
    current_user = result.scalar_one_or_none()
    
    if not current_user:
        raise HTTPException(status_code=401, detail="User not found")
    
    # Verify document exists and is active
    doc_result = await db.execute(
        select(InductionDocument).where(
            InductionDocument.id == request.document_id,
            InductionDocument.is_active == True
        )
    )
    document = doc_result.scalar_one_or_none()
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Check if already signed
    existing_result = await db.execute(
        select(UserInduction).where(
            UserInduction.user_id == current_user.id,
            UserInduction.document_id == request.document_id,
            UserInduction.status == "signed"
        )
    )
    existing = existing_result.scalar_one_or_none()
    
    if existing:
        raise HTTPException(status_code=400, detail="Document already signed")
    
    # Create signed record
    user_induction = UserInduction(
        user_id=current_user.id,
        document_id=request.document_id,
        signature=request.signature,
        signed_at=datetime.utcnow(),
        status="signed"
    )
    
    db.add(user_induction)
    await db.commit()
    
    return {
        "message": "Document signed successfully",
        "document_title": document.title
    }


# ============ ADMIN ENDPOINTS ============

@router.get("/admin/all-status")
async def get_all_induction_status(
    db: AsyncSession = Depends(get_db)
):
    """Get induction status for all users (admin view)"""
    # Get all active users
    users_result = await db.execute(
        select(User).where(User.is_active == True).order_by(User.surname, User.first_name)
    )
    users = users_result.scalars().all()
    
    # Get required document count
    required_result = await db.execute(
        select(func.count()).select_from(InductionDocument)
        .where(InductionDocument.is_active == True, InductionDocument.is_required == True)
    )
    total_required = required_result.scalar() or 0
    
    user_statuses = []
    for user in users:
        # Count signed required documents
        signed_result = await db.execute(
            select(func.count()).select_from(UserInduction)
            .join(InductionDocument)
            .where(
                UserInduction.user_id == user.id,
                UserInduction.status == "signed",
                InductionDocument.is_required == True
            )
        )
        signed_count = signed_result.scalar() or 0
        
        user_statuses.append({
            "user_id": user.id,
            "user_name": f"{user.first_name} {user.surname}",
            "user_email": user.email,
            "total_required": total_required,
            "total_signed": signed_count,
            "is_complete": signed_count >= total_required,
            "completion_percentage": round((signed_count / total_required * 100) if total_required > 0 else 100)
        })
    
    return {"users": user_statuses}


@router.get("/admin/user/{user_id}/details")
async def get_user_induction_details(
    user_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get detailed induction status for a specific user (admin view)"""
    # Get user
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Get all documents
    docs_result = await db.execute(
        select(InductionDocument)
        .where(InductionDocument.is_active == True)
        .order_by(InductionDocument.display_order)
    )
    documents = docs_result.scalars().all()
    
    # Get user's signatures
    signed_result = await db.execute(
        select(UserInduction).where(UserInduction.user_id == user_id)
    )
    signed_map = {ui.document_id: ui for ui in signed_result.scalars().all()}
    
    doc_details = []
    for doc in documents:
        signed = signed_map.get(doc.id)
        doc_details.append({
            "document_id": doc.id,
            "title": doc.title,
            "document_type": doc.document_type,
            "category": doc.category,
            "is_required": doc.is_required,
            "status": signed.status if signed else "pending",
            "signed_at": signed.signed_at.isoformat() if signed and signed.signed_at else None,
            "signature": signed.signature if signed else None,
        })
    
    return {
        "user": {
            "id": user.id,
            "name": f"{user.first_name} {user.surname}",
            "email": user.email
        },
        "documents": doc_details
    }


@router.post("/admin/documents")
async def create_document(
    title: str,
    content: Optional[str] = None,
    description: Optional[str] = None,
    document_type: str = "swms",
    category: Optional[str] = None,
    is_required: bool = True,
    display_order: int = 0,
    db: AsyncSession = Depends(get_db)
):
    """Create a new induction document with text content (admin)"""
    if not content:
        raise HTTPException(status_code=400, detail="Content is required for text documents")
    
    document = InductionDocument(
        title=title,
        description=description,
        content=content,
        document_type=document_type,
        category=category,
        is_required=is_required,
        display_order=display_order
    )
    
    db.add(document)
    await db.commit()
    await db.refresh(document)
    
    return {
        "message": "Document created successfully",
        "document_id": document.id
    }


@router.post("/admin/documents/upload-pdf")
async def create_document_with_pdf(
    title: str = Form(...),
    pdf_file: UploadFile = File(...),
    description: Optional[str] = Form(None),
    document_type: str = Form("swms"),
    category: Optional[str] = Form(None),
    is_required: str = Form("true"),
    display_order: int = Form(0),
    db: AsyncSession = Depends(get_db)
):
    """Create a new induction document with PDF upload (admin)"""
    # Convert is_required string to boolean
    is_required_bool = is_required.lower() in ("true", "1", "yes", "on")
    
    # Validate file type
    if not pdf_file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    
    # Generate unique filename
    file_ext = os.path.splitext(pdf_file.filename)[1]
    unique_filename = f"{uuid.uuid4()}{file_ext}"
    file_path = os.path.join(PDF_STORAGE_DIR, unique_filename)
    
    # Save the file
    try:
        contents = await pdf_file.read()
        with open(file_path, "wb") as f:
            f.write(contents)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save PDF: {str(e)}")
    
    # Create database record
    document = InductionDocument(
        title=title,
        description=description,
        content=None,  # No text content for PDF documents
        document_type=document_type,
        category=category,
        is_required=is_required_bool,
        display_order=display_order,
        pdf_filename=unique_filename
    )
    
    db.add(document)
    await db.commit()
    await db.refresh(document)
    
    return {
        "message": "PDF document uploaded successfully",
        "document_id": document.id,
        "pdf_url": f"/api/induction/pdf/{unique_filename}"
    }


@router.delete("/admin/documents/{document_id}")
async def deactivate_document(
    document_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Deactivate an induction document (admin)"""
    result = await db.execute(
        select(InductionDocument).where(InductionDocument.id == document_id)
    )
    document = result.scalar_one_or_none()
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    document.is_active = False
    await db.commit()
    
    return {"message": "Document deactivated"}
