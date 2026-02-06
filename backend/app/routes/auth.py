"""
RAW Labour Hire - Authentication API
"""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
import hashlib
import os
import secrets

from ..database import get_db
from ..models import User, UserRole
from ..email import send_password_reset_email
from ..services.sms import send_sms

router = APIRouter()

# Security config
SECRET_KEY = "your-secret-key-change-in-production"  # TODO: Move to env
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 1 week

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


# === Pydantic Models ===

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    first_name: str
    surname: str
    phone: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class UserResponse(BaseModel):
    id: int
    email: str
    first_name: str
    surname: str
    phone: Optional[str]
    role: str
    is_active: bool


# === Helper Functions ===

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if user is None:
        raise credentials_exception
    return user


# === Routes ===

@router.post("/register", response_model=UserResponse)
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    """Register a new user/worker"""
    password = user_data.password.strip()
    if len(password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 6 characters"
        )
    if len(password) > 72:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be 72 characters or fewer"
        )

    # Check if email exists
    result = await db.execute(select(User).where(User.email == user_data.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create user
    user = User(
        email=user_data.email,
        hashed_password=get_password_hash(password),
        first_name=user_data.first_name,
        surname=user_data.surname,
        phone=user_data.phone,
        role=UserRole.WORKER
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    return UserResponse(
        id=user.id,
        email=user.email,
        first_name=user.first_name,
        surname=user.surname,
        phone=user.phone,
        role=user.role.value,
        is_active=user.is_active
    )


@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """Login and get access token"""
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled"
        )
    
    access_token = create_access_token(
        data={"sub": user.id},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    return Token(
        access_token=access_token,
        user={
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "surname": user.surname,
            "role": user.role.value
        }
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current user profile"""
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        first_name=current_user.first_name,
        surname=current_user.surname,
        phone=current_user.phone,
        role=current_user.role.value,
        is_active=current_user.is_active
    )


class UpdateProfileRequest(BaseModel):
    first_name: Optional[str] = None
    surname: Optional[str] = None
    phone: Optional[str] = None
    date_of_birth: Optional[str] = None
    # Address
    address: Optional[str] = None
    suburb: Optional[str] = None
    state: Optional[str] = None
    postcode: Optional[str] = None
    # Emergency contact
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    emergency_contact_relationship: Optional[str] = None
    # Bank details
    bank_account_name: Optional[str] = None
    bank_bsb: Optional[str] = None
    bank_account_number: Optional[str] = None
    tax_file_number: Optional[str] = None
    # Employment
    employment_type: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


def user_to_dict(user: User) -> dict:
    """Convert user model to dictionary with all extended fields"""
    return {
        "id": user.id,
        "email": user.email,
        "first_name": user.first_name,
        "surname": user.surname,
        "phone": user.phone,
        "role": user.role.value,
        "date_of_birth": user.date_of_birth.isoformat() if user.date_of_birth else None,
        "start_date": user.start_date.isoformat() if user.start_date else None,
        # Address
        "address": user.address,
        "suburb": user.suburb,
        "state": user.state,
        "postcode": user.postcode,
        # Emergency contact
        "emergency_contact_name": user.emergency_contact_name,
        "emergency_contact_phone": user.emergency_contact_phone,
        "emergency_contact_relationship": user.emergency_contact_relationship,
        # Bank details
        "bank_account_name": user.bank_account_name,
        "bank_bsb": user.bank_bsb,
        "bank_account_number": user.bank_account_number,
        "tax_file_number": user.tax_file_number,
        # Employment
        "employment_type": user.employment_type,
        "is_active": user.is_active,
    }


@router.patch("/update-profile")
async def update_profile(
    data: UpdateProfileRequest,
    user_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    """Update user profile information"""
    # Use provided user_id or fall back to first user (temp auth bypass)
    if user_id:
        result = await db.execute(select(User).where(User.id == user_id))
    else:
        result = await db.execute(select(User).limit(1))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Personal info
    if data.first_name is not None:
        user.first_name = data.first_name.strip()
    if data.surname is not None:
        user.surname = data.surname.strip()
    if data.phone is not None:
        user.phone = data.phone.strip() if data.phone else None
    if data.date_of_birth is not None:
        from datetime import datetime
        try:
            # Try multiple date formats
            for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"]:
                try:
                    user.date_of_birth = datetime.strptime(data.date_of_birth, fmt).date()
                    break
                except ValueError:
                    continue
        except:
            pass
    
    # Address
    if data.address is not None:
        user.address = data.address.strip() if data.address else None
    if data.suburb is not None:
        user.suburb = data.suburb.strip() if data.suburb else None
    if data.state is not None:
        user.state = data.state.strip().upper() if data.state else None
    if data.postcode is not None:
        user.postcode = data.postcode.strip() if data.postcode else None
    
    # Emergency contact
    if data.emergency_contact_name is not None:
        user.emergency_contact_name = data.emergency_contact_name.strip() if data.emergency_contact_name else None
    if data.emergency_contact_phone is not None:
        user.emergency_contact_phone = data.emergency_contact_phone.strip() if data.emergency_contact_phone else None
    if data.emergency_contact_relationship is not None:
        user.emergency_contact_relationship = data.emergency_contact_relationship.strip() if data.emergency_contact_relationship else None
    
    # Bank details
    if data.bank_account_name is not None:
        user.bank_account_name = data.bank_account_name.strip() if data.bank_account_name else None
    if data.bank_bsb is not None:
        user.bank_bsb = data.bank_bsb.strip() if data.bank_bsb else None
    if data.bank_account_number is not None:
        user.bank_account_number = data.bank_account_number.strip() if data.bank_account_number else None
    if data.tax_file_number is not None:
        user.tax_file_number = data.tax_file_number.strip() if data.tax_file_number else None
    
    # Employment
    if data.employment_type is not None:
        user.employment_type = data.employment_type
    
    await db.commit()
    await db.refresh(user)
    
    return {
        "message": "Profile updated successfully",
        "user": user_to_dict(user)
    }


@router.post("/change-password")
async def change_password(
    data: ChangePasswordRequest,
    user_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    """Change user password"""
    # Use provided user_id or fall back to first user (temp auth bypass)
    if user_id:
        result = await db.execute(select(User).where(User.id == user_id))
    else:
        result = await db.execute(select(User).limit(1))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Verify current password
    if not verify_password(data.current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )
    
    # Validate new password
    new_password = data.new_password.strip()
    if len(new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 6 characters"
        )
    if len(new_password) > 72:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be 72 characters or fewer"
        )
    
    # Update password
    user.hashed_password = get_password_hash(new_password)
    await db.commit()
    
    return {"message": "Password changed successfully"}


@router.post("/password-reset/request")
async def request_password_reset(
    data: PasswordResetRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Send a password reset code via SMS if the user exists"""
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if not user:
        return {"message": "If an account exists, a reset code has been sent via SMS."}

    # Check if user has a phone number
    if not user.phone:
        return {"message": "If an account exists, a reset code has been sent via SMS."}

    # Generate a 6-digit code (easier to enter than a long token)
    reset_code = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
    token_hash = hashlib.sha256(reset_code.encode()).hexdigest()
    expires_at = datetime.utcnow() + timedelta(minutes=15)  # 15 min expiry for SMS codes

    user.reset_token_hash = token_hash
    user.reset_token_expires_at = expires_at
    user.reset_token_used_at = None
    await db.commit()

    # Send SMS with reset code
    sms_message = f"RAW Labour Hire: Your password reset code is {reset_code}. This code expires in 15 minutes."
    
    async def send_reset_sms():
        await send_sms(user.phone, sms_message)
    
    background_tasks.add_task(send_reset_sms)

    return {"message": "If an account exists, a reset code has been sent via SMS."}


@router.post("/password-reset/confirm")
async def confirm_password_reset(
    data: PasswordResetConfirm,
    db: AsyncSession = Depends(get_db)
):
    """Confirm a password reset using a token"""
    new_password = data.new_password.strip()
    if len(new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 6 characters"
        )
    if len(new_password) > 72:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be 72 characters or fewer"
        )

    token_hash = hashlib.sha256(data.token.encode()).hexdigest()
    result = await db.execute(select(User).where(User.reset_token_hash == token_hash))
    user = result.scalar_one_or_none()

    if not user or not user.reset_token_expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )

    if user.reset_token_used_at or user.reset_token_expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )

    user.hashed_password = get_password_hash(new_password)
    user.reset_token_used_at = datetime.utcnow()
    user.reset_token_hash = None
    user.reset_token_expires_at = None
    await db.commit()

    return {"message": "Password reset successful"}


# === Admin Dashboard Login ===

class AdminLogin(BaseModel):
    username: str
    password: str


@router.post("/admin/login")
async def admin_login(data: AdminLogin):
    """Login endpoint for admin dashboard"""
    # Get admin credentials from environment variables
    # Default credentials for development - CHANGE IN PRODUCTION
    admin_username = os.getenv("ADMIN_USERNAME", "admin")
    admin_password = os.getenv("ADMIN_PASSWORD", "RAWadmin2024!")
    
    if data.username == admin_username and data.password == admin_password:
        # Generate a simple token
        token = jwt.encode(
            {
                "sub": "admin",
                "type": "admin",
                "exp": datetime.utcnow() + timedelta(hours=24)
            },
            SECRET_KEY,
            algorithm=ALGORITHM
        )
        return {
            "success": True,
            "token": token,
            "username": admin_username
        }
    
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid username or password"
    )


@router.get("/admin/verify")
async def verify_admin_token(token: str):
    """Verify admin token is valid"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") == "admin":
            return {"valid": True, "username": payload.get("sub")}
    except JWTError:
        pass
    
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token"
    )
