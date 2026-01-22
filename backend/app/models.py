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
from sqlalchemy.orm import relationship, DeclarativeBase
from enum import Enum


class Base(DeclarativeBase):
    pass


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
    
    # Role
    role = Column(SQLEnum(UserRole), default=UserRole.WORKER)
    
    # Status
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    timesheets = relationship("Timesheet", back_populates="worker")
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
    myob_customer_id = Column(String(100))
    
    # Billing rates
    default_hourly_rate = Column(Float, default=0)
    default_overtime_rate = Column(Float, default=0)
    
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
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)
    
    name = Column(String(200), nullable=False)
    address = Column(Text, nullable=False)  # Job Address from timesheet
    
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
    
    # Supervisor approval (from paper form)
    supervisor_id = Column(Integer, ForeignKey("users.id"))
    supervisor_signature = Column(Text)  # Base64 encoded signature image
    supervisor_signed_at = Column(DateTime)
    supervisor_contact = Column(String(20))
    
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
    
    # Relationships
    timesheet = relationship("Timesheet", back_populates="entries")
    job_site = relationship("JobSite", back_populates="timesheet_entries")


# ==================== MYOB EXPORT ====================

class MYOBExport(Base):
    """Track exports to MYOB for billing"""
    __tablename__ = "myob_exports"
    
    id = Column(Integer, primary_key=True, index=True)
    timesheet_id = Column(Integer, ForeignKey("timesheets.id"), nullable=False)
    
    # Export details
    exported_at = Column(DateTime, default=datetime.utcnow)
    myob_invoice_id = Column(String(100))
    export_status = Column(String(50))  # success, failed, pending
    error_message = Column(Text)
    
    # Invoice details
    invoice_amount = Column(Float)
    invoice_date = Column(Date)
