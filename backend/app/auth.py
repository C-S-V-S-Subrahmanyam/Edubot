from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
import hashlib
import secrets
import uuid
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from app.config import (
    JWT_SECRET_KEY,
    JWT_ALGORITHM,
    JWT_EXPIRY,
    ADMIN_EMAIL_DOMAIN,
    ADMIN_OVERRIDE_USERNAMES,
)
from app.db.models import User
from app.db.database import get_session

# Bearer token security
security = HTTPBearer()


def hash_password(password: str) -> str:
    """Hash a password using PBKDF2 (Python 3.14 compatible)."""
    # Generate a random salt
    salt = secrets.token_hex(16)
    # Hash the password with the salt
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000)
    # Return salt and hash combined
    return f"{salt}${pwd_hash.hex()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash."""
    try:
        salt, pwd_hash = hashed_password.split('$')
        # Hash the provided password with the stored salt
        pwd_hash_check = hashlib.pbkdf2_hmac('sha256', plain_password.encode('utf-8'), salt.encode('utf-8'), 100000)
        return pwd_hash == pwd_hash_check.hex()
    except Exception:
        return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRY)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> dict:
    """Decode and verify a JWT access token."""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def has_permission(current_user: dict, permission: str) -> bool:
    """Return True if user has the permission (admins always pass)."""
    if current_user.get("is_admin"):
        return True
    user_perms = current_user.get("permissions") or []
    return permission in user_perms


def require_permission(permission: str):
    """FastAPI dependency factory for permission checks."""
    async def _checker(current_user: dict = Depends(get_current_user)) -> dict:
        if not has_permission(current_user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission required: {permission}",
            )
        return current_user

    return _checker


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Dependency to get the current authenticated user.
    Returns user data as dict.
    """
    token = credentials.credentials
    payload = decode_access_token(token)
    
    user_id_str: str = payload.get("sub")
    if user_id_str is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )
    
    # Convert string UUID to UUID object
    try:
        user_id = uuid.UUID(user_id_str)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user ID format",
        )
    
    # Fetch user from database with one retry for transient connection drops.
    user = None
    for attempt in range(2):
        try:
            result = await session.execute(
                select(User).where(User.id == user_id, User.is_active == True)
            )
            user = result.scalar_one_or_none()
            break
        except DBAPIError as e:
            await session.rollback()
            if attempt == 0 and getattr(e, "connection_invalidated", False):
                continue
            raise
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    
    return {
        "user_id": str(user.id),
        "username": user.username,
        "email": user.email,
        "is_admin": user.is_admin,
        "permissions": user.permissions or [],
    }


async def get_current_admin_user(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """
    Dependency to get the current user and verify they are an admin.
    Only users with @pvpsiddhartha.ac.in email domain can be admins.
    """
    # Check if user has admin privileges
    if not current_user.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    
    # Verify the email domain or explicit username override
    email = current_user.get("email", "")
    username = str(current_user.get("username", "")).lower()
    if not email.endswith(ADMIN_EMAIL_DOMAIN) and username not in ADMIN_OVERRIDE_USERNAMES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Admin access is restricted to {ADMIN_EMAIL_DOMAIN} domain "
                f"or approved admin usernames"
            ),
        )
    
    return current_user
