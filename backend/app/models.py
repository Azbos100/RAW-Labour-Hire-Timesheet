"""
RAW Labour Hire - Database Models
Based on the paper timesheet format
"""

from datetime import datetime, date, time
from typing import Optional, List
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Date, Time,
    ForeignKey, Text, Enum as SQLEnum
)
from sqlalchemy.orm import relationship
from enum import Enum

from .database import Base


class UserRole(str, Enum):
    WORKER = "worker"
    SUPERVISOR = "supervisor"
    ADMIN = "admin"


class TimesheetStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"


class InjuryStatus(str, Enum):
    YES = "yes"
    NO = "no"
    NA = "n/a"


# ==================== USERS ====================

class User(Base):
    """Staff/Employee model"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    
    # Personal Info (from timesheet header)
    first_name = Column(String(100), nullable=False)
    surname = Column(String(100), nullable=False)
    phone = Column(String(20))
    
    # Extended Personal Info
    address = Column(Text)
    suburb = Column(String(100))
    state = Column(String(20))
    postcode = Column(String(10))
    date_of_birth = Column(Date)
    start_date = Column(Date)
    
    # Emergency Contact / Next of Kin
    emergency_contact_name = Column(String(100))
    emergency_contact_phone = Column(String(20))
    emergency_contact_relationship = Column(String(50))
    
    # Bank Details for Payment
    bank_account_name = Column(String(100))
    bank_bsb = Column(String(10))
    bank_account_number = Column(String(20))
    
    # Tax
    tax_file_number = Column(String(20))
    
    # Employment Type
    employment_type = Column(String(20), default="casual")  # casual, full_time, part_time
    
    # Role
    role = Column(SQLEnum(UserRole), default=UserRole.WORKER)
    
    # Status
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Password reset
    reset_token_hash = Column(String(64), index=True)
    reset_token_expires_at = Column(DateTime)
    reset_token_used_at = Column(DateTime)
    
    # Pay Rates (for MYOB payroll)
    base_pay_rate = Column(Float, default=0)      # Normal hourly rate
    overtime_pay_rate = Column(Float, default=0)  # Overtime rate (1.5x typically)
    weekend_pay_rate = Column(Float, default=0)   # Weekend rate
    night_pay_rate = Column(Float, default=0)     # Night shift rate
    
    # MYOB Integration
    myob_employee_id = Column(String(100))  # MYOB Employee UID
    
    # Relationships
    timesheets = relationship(
        "Timesheet",
        back_populates="worker",
        foreign_keys="Timesheet.worker_id",
    )
    supervised_timesheets = relationship("Timesheet", back_populates="supervisor", 
                                         foreign_keys="Timesheet.supervisor_id")


# ==================== CLIENTS ====================

class Client(Base):
    """Client company that we bill"""
    __tablename__ = "clients"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    contact_name = Column(String(100))
    contact_email = Column(String(255))
    contact_phone = Column(String(20))
    address = Column(Text)
    
    # MYOB Integration
    myob_customer_id = Column(String(100))  # MYOB Customer UID
    
    # Billing rates (charged to client)
    hourly_billing_rate = Column(Float, default=0)     # Standard hourly rate billed to client
    overtime_billing_rate = Column(Float, default=0)   # Overtime rate billed
    weekend_billing_rate = Column(Float, default=0)    # Weekend rate billed
    night_billing_rate = Column(Float, default=0)      # Night shift rate billed
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    job_sites = relationship("JobSite", back_populates="client")
    timesheets = relationship("Timesheet", back_populates="client")


# ==================== JOB SITES ====================

class JobSite(Base):
    """Job site/location where work is performed"""
    __tablename__ = "job_sites"
    
    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True)  # Optional client
    
    name = Column(String(200), nullable=False)
    address = Column(Text, nullable=False)  # Job Address from timesheet
    
    # Site contact details
    contact_name = Column(String(100))
    contact_phone = Column(String(20))
    
    # GPS coordinates for geofencing
    latitude = Column(Float)
    longitude = Column(Float)
    geofence_radius = Column(Integer, default=100)  # meters
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    client = relationship("Client", back_populates="job_sites")
    timesheet_entries = relationship("TimesheetEntry", back_populates="job_site")


# ==================== TIMESHEETS ====================

class Timesheet(Base):
    """Weekly timesheet (matches paper form)"""
    __tablename__ = "timesheets"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Docket Number (from paper form - auto-generated)
    docket_number = Column(String(20), unique=True, index=True)
    
    # Order Number (optional)
    order_number = Column(String(50))
    
    # Worker
    worker_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Client
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)
    
    # Week info
    week_starting = Column(Date, nullable=False)  # Monday of the week
    week_ending = Column(Date, nullable=False)    # Sunday of the week
    
    # Status
    status = Column(SQLEnum(TimesheetStatus), default=TimesheetStatus.DRAFT)
    
    # Host company (where worker performed the job)
    host_company_name = Column(String(200))
    
    # Supervisor approval (from paper form)
    supervisor_id = Column(Integer, ForeignKey("users.id"))
    supervisor_name = Column(String(100))  # Supervisor's name
    supervisor_signature = Column(Text)  # Base64 encoded signature image
    supervisor_signed_at = Column(DateTime)
    supervisor_contact = Column(String(50))
    
    # Injury notification
    injury_reported = Column(SQLEnum(InjuryStatus), default=InjuryStatus.NA)
    
    # Totals (calculated)
    total_ordinary_hours = Column(Float, default=0)
    total_overtime_hours = Column(Float, default=0)
    total_hours = Column(Float, default=0)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    submitted_at = Column(DateTime)
    
    # Relationships
    worker = relationship("User", back_populates="timesheets", foreign_keys=[worker_id])
    supervisor = relationship("User", back_populates="supervised_timesheets", 
                             foreign_keys=[supervisor_id])
    client = relationship("Client", back_populates="timesheets")
    entries = relationship("TimesheetEntry", back_populates="timesheet", 
                          cascade="all, delete-orphan")


# ==================== TIMESHEET ENTRIES ====================

class TimesheetEntry(Base):
    """Daily entry within a timesheet (one row per day on paper form)"""
    __tablename__ = "timesheet_entries"
    
    id = Column(Integer, primary_key=True, index=True)
    timesheet_id = Column(Integer, ForeignKey("timesheets.id"), nullable=False)
    
    # Day info
    day_of_week = Column(String(10), nullable=False)  # MON, TUE, WED, etc.
    entry_date = Column(Date, nullable=False)
    
    # Job Site
    job_site_id = Column(Integer, ForeignKey("job_sites.id"))
    
    # Times
    time_start = Column(Time)
    time_finish = Column(Time)
    
    # Hours (from paper form)
    ordinary_hours = Column(Float, default=0)
    overtime_hours = Column(Float, default=0)
    total_hours = Column(Float, default=0)
    
    # GPS Clock In/Out
    clock_in_time = Column(DateTime)
    clock_in_latitude = Column(Float)
    clock_in_longitude = Column(Float)
    clock_in_address = Column(Text)  # Reverse geocoded address
    
    clock_out_time = Column(DateTime)
    clock_out_latitude = Column(Float)
    clock_out_longitude = Column(Float)
    clock_out_address = Column(Text)
    
    # Additional fields from paper form
    worked_as = Column(String(100))  # Job role/position
    first_aid_injury = Column(Boolean, default=False)
    comments = Column(Text)
    
    # Individual entry submission (for daily approval)
    entry_status = Column(String(20), default="draft")  # draft, submitted, approved, rejected
    host_company_name = Column(String(200))
    supervisor_name = Column(String(100))
    supervisor_contact = Column(String(50))
    supervisor_signature = Column(Text)  # Base64 encoded
    submitted_at = Column(DateTime)
    
    # Relationships
    timesheet = relationship("Timesheet", back_populates="entries")
    job_site = relationship("JobSite", back_populates="timesheet_entries")


# ==================== USER TICKETS/CERTIFICATIONS ====================

class TicketType(Base):
    """Types of tickets/certifications (White Card, WWC, etc.)"""
    __tablename__ = "ticket_types"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)  # e.g., "White Card", "Working with Children"
    description = Column(Text)
    has_expiry = Column(Boolean, default=True)  # Whether this ticket expires
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user_tickets = relationship("UserTicket", back_populates="ticket_type")


class UserTicket(Base):
    """User's uploaded tickets/certifications"""
    __tablename__ = "user_tickets"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    ticket_type_id = Column(Integer, ForeignKey("ticket_types.id"), nullable=False)
    
    # Ticket details
    ticket_number = Column(String(100))  # License/certificate number
    issue_date = Column(Date)
    expiry_date = Column(Date)  # Null if doesn't expire
    
    # Image of the ticket (Base64 encoded)
    front_image = Column(Text)
    back_image = Column(Text)  # Optional back of card
    
    # Status
    status = Column(String(20), default="pending")  # pending, verified, expired, rejected
    verified_at = Column(DateTime)
    verified_by = Column(Integer, ForeignKey("users.id"))
    
    notes = Column(Text)  # Admin notes
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    ticket_type = relationship("TicketType", back_populates="user_tickets")
    verifier = relationship("User", foreign_keys=[verified_by])


# ==================== INDUCTION / SWMS ====================

class InductionDocument(Base):
    """SWMS and induction documents that need to be signed"""
    __tablename__ = "induction_documents"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Document info
    title = Column(String(200), nullable=False)  # e.g., "General Site Safety SWMS"
    description = Column(Text)  # Brief description
    content = Column(Text, nullable=True)  # Full document content (HTML or plain text) - nullable if PDF
    document_type = Column(String(50), default="swms")  # swms, induction, policy
    
    # PDF file storage
    pdf_filename = Column(String(255))  # Filename of uploaded PDF
    
    # Categorization
    category = Column(String(100))  # e.g., "Safety", "Manual Handling", "PPE"
    
    # Version control
    version = Column(String(20), default="1.0")
    
    # Status
    is_required = Column(Boolean, default=True)  # Must be signed during onboarding
    is_active = Column(Boolean, default=True)
    
    # Order for display
    display_order = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user_inductions = relationship("UserInduction", back_populates="document")


class UserInduction(Base):
    """Tracks which induction documents a user has signed"""
    __tablename__ = "user_inductions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    document_id = Column(Integer, ForeignKey("induction_documents.id"), nullable=False)
    
    # Signature
    signature = Column(Text)  # Base64 encoded signature image
    signed_at = Column(DateTime)
    
    # Status
    status = Column(String(20), default="pending")  # pending, signed, expired
    
    # Device/location info for audit
    signed_ip = Column(String(50))
    signed_device = Column(String(200))
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User")
    document = relationship("InductionDocument", back_populates="user_inductions")


# ==================== MYOB INTEGRATION ====================

class MYOBSettings(Base):
    """MYOB API credentials and settings"""
    __tablename__ = "myob_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # OAuth2 Credentials
    client_id = Column(String(255))
    client_secret = Column(String(255))
    
    # OAuth2 Tokens
    access_token = Column(Text)
    refresh_token = Column(Text)
    token_expires_at = Column(DateTime)
    
    # Company File
    company_file_id = Column(String(255))
    company_file_name = Column(String(255))
    company_file_uri = Column(Text)
    
    # Status
    is_connected = Column(Boolean, default=False)
    last_sync_at = Column(DateTime)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MYOBExport(Base):
    """Track exports to MYOB for billing and payroll"""
    __tablename__ = "myob_exports"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Can link to either timesheet or entry
    timesheet_id = Column(Integer, ForeignKey("timesheets.id"))
    entry_id = Column(Integer, ForeignKey("timesheet_entries.id"))
    
    # Export type
    export_type = Column(String(50))  # invoice, timesheet, payroll
    
    # Export details
    exported_at = Column(DateTime, default=datetime.utcnow)
    exported_by = Column(Integer, ForeignKey("users.id"))
    
    # MYOB references
    myob_invoice_id = Column(String(100))
    myob_timesheet_id = Column(String(100))
    myob_activity_id = Column(String(100))
    
    export_status = Column(String(50))  # success, failed, pending
    error_message = Column(Text)
    
    # Invoice details
    invoice_amount = Column(Float)
    invoice_date = Column(Date)
    
    # Payroll details
    pay_amount = Column(Float)
    hours_exported = Column(Float)


# ==================== NOTIFICATION SETTINGS ====================

class NotificationSettings(Base):
    """Global notification settings"""
    __tablename__ = "notification_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Clock-in reminder
    clock_in_reminder_enabled = Column(Boolean, default=True)
    clock_in_reminder_time = Column(Time, default=time(7, 0))  # 7:00 AM
    
    # Clock-out reminder
    clock_out_reminder_enabled = Column(Boolean, default=True)
    clock_out_reminder_time = Column(Time, default=time(17, 0))  # 5:00 PM
    
    # SMS settings
    sms_enabled = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
