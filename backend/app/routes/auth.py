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


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


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
    
    if data.first_name is not None:
        user.first_name = data.first_name.strip()
    if data.surname is not None:
        user.surname = data.surname.strip()
    if data.phone is not None:
        user.phone = data.phone.strip() if data.phone else None
    
    await db.commit()
    await db.refresh(user)
    
    return {
        "message": "Profile updated successfully",
        "user": {
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "surname": user.surname,
            "phone": user.phone,
            "role": user.role.value
        }
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
    """Send a password reset email if the user exists"""
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if not user:
        return {"message": "If an account exists, a reset email has been sent."}

    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expires_at = datetime.utcnow() + timedelta(hours=1)

    user.reset_token_hash = token_hash
    user.reset_token_expires_at = expires_at
    user.reset_token_used_at = None
    await db.commit()

    reset_url_base = os.getenv("RESET_URL_BASE", "http://localhost:3000/reset-password")
    reset_link = f"{reset_url_base}?token={token}"

    background_tasks.add_task(
        send_password_reset_email,
        to_email=user.email,
        reset_link=reset_link,
        token=token,
    )

    return {"message": "If an account exists, a reset email has been sent."}


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
