from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
import uuid
from app.db.database import get_session
from app.db.models import User
from app.schemas import (
    UserRegister, UserLogin, Token, UserResponse,
    SendOTPRequest, SendOTPResponse, VerifyOTPRequest, VerifyOTPResponse,
    ForgotPasswordRequest, ForgotPasswordResponse, VerifyResetOTPRequest, ResetPasswordRequest
)
from app.auth import hash_password, verify_password, create_access_token, get_current_user
from app.email_service import send_otp_email, verify_otp, send_welcome_email, send_password_reset_otp_email, verify_password_reset_otp
from app.config import RESTRICTED_EMAIL_DOMAIN, ADMIN_EMAIL_DOMAIN

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Allowed email domains derived from config
ALLOWED_DOMAINS = [
    RESTRICTED_EMAIL_DOMAIN.lstrip('@'),
    ADMIN_EMAIL_DOMAIN.lstrip('@'),
]

def validate_email_domain(email: str) -> None:
    """Validate that the email belongs to an allowed domain."""
    email_domain = email.split('@')[-1]
    if email_domain not in ALLOWED_DOMAINS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only @{' and @'.join(ALLOWED_DOMAINS)} email addresses are allowed",
        )


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserRegister,
    session: AsyncSession = Depends(get_session),
):
    """Register a new user."""
    
    # Check email domain
    validate_email_domain(user_data.email)
    
    # Check if username or email already exists
    result = await session.execute(
        select(User).where(
            (User.username == user_data.username) | (User.email == user_data.email)
        )
    )
    existing_user = result.scalar_one_or_none()
    
    if existing_user:
        if existing_user.username == user_data.username:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already registered",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )
    
    # Create new user
    # Auto-grant admin privileges to admin-domain users
    is_admin = user_data.email.endswith(ADMIN_EMAIL_DOMAIN)
    hashed_pw = hash_password(user_data.password)
    new_user = User(
        email=user_data.email,
        username=user_data.username,
        hashed_password=hashed_pw,
        is_admin=is_admin,
    )
    
    session.add(new_user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already registered",
        )
    await session.refresh(new_user)
    
    # Create access token
    access_token = create_access_token(data={"sub": str(new_user.id)})
    
    user_response = UserResponse.model_validate(new_user)
    
    return Token(access_token=access_token, user=user_response)


@router.post("/login", response_model=Token)
async def login(
    user_data: UserLogin,
    session: AsyncSession = Depends(get_session),
):
    """Login user and return access token."""
    
    # Find user by email
    result = await session.execute(
        select(User).where(User.email == user_data.email)
    )
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(user_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )
    
    # Create access token
    access_token = create_access_token(data={"sub": str(user.id)})
    
    user_response = UserResponse.model_validate(user)
    
    return Token(access_token=access_token, user=user_response)


@router.post("/send-otp", response_model=SendOTPResponse)
async def send_otp(
    data: SendOTPRequest,
    session: AsyncSession = Depends(get_session),
):
    """Send OTP to email for verification before registration."""
    
    # Check email domain
    validate_email_domain(data.email)
    
    # Check if username or email already exists
    result = await session.execute(
        select(User).where(
            (User.username == data.username) | (User.email == data.email)
        )
    )
    existing_user = result.scalar_one_or_none()
    
    if existing_user:
        if existing_user.username == data.username:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already registered",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )
    
    # Send OTP email (password is hashed before storing with OTP)
    hashed_pw = hash_password(data.password)
    sent = send_otp_email(data.email, data.username, hashed_pw)
    
    if not sent:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send verification email. Please try again.",
        )
    
    return SendOTPResponse(success=True, message="Verification code sent to your email")


@router.post("/verify-otp", response_model=Token, status_code=status.HTTP_201_CREATED)
async def verify_otp_and_register(
    data: VerifyOTPRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    """Verify OTP and complete registration."""
    
    # Verify OTP and get stored data
    stored_data = verify_otp(data.email, data.otp)
    
    if not stored_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code. Please request a new one.",
        )
    
    username = stored_data['username']
    hashed_pw = stored_data['hashed_password']
    
    # Create new user with pre-hashed password
    is_admin = data.email.endswith(ADMIN_EMAIL_DOMAIN)
    new_user = User(
        email=data.email,
        username=username,
        hashed_password=hashed_pw,
        is_admin=is_admin,
    )
    
    session.add(new_user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already registered",
        )
    await session.refresh(new_user)
    
    # Send welcome email in background
    background_tasks.add_task(send_welcome_email, data.email, username)
    
    # Create access token
    access_token = create_access_token(data={"sub": str(new_user.id)})
    
    user_response = UserResponse.model_validate(new_user)
    
    return Token(access_token=access_token, user=user_response)


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """Get current user information."""
    
    result = await session.execute(
        select(User).where(User.id == uuid.UUID(current_user["user_id"]))
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    return UserResponse.model_validate(user)


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
async def forgot_password(
    data: ForgotPasswordRequest,
    session: AsyncSession = Depends(get_session),
):
    """Send OTP to email for password reset."""
    
    # Find user by email
    result = await session.execute(
        select(User).where(User.email == data.email)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        # Don't reveal whether email exists - still return success
        return ForgotPasswordResponse(
            success=True,
            message="If an account with that email exists, a reset code has been sent."
        )
    
    if not user.is_active:
        return ForgotPasswordResponse(
            success=True,
            message="If an account with that email exists, a reset code has been sent."
        )
    
    # Send password reset OTP
    sent = send_password_reset_otp_email(data.email, user.username)
    
    if not sent:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send reset email. Please try again.",
        )
    
    return ForgotPasswordResponse(
        success=True,
        message="If an account with that email exists, a reset code has been sent."
    )


@router.post("/reset-password", response_model=ForgotPasswordResponse)
async def reset_password(
    data: ResetPasswordRequest,
    session: AsyncSession = Depends(get_session),
):
    """Verify OTP and reset the user's password."""
    
    # Verify the OTP
    is_valid = verify_password_reset_otp(data.email, data.otp)
    
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset code. Please request a new one.",
        )
    
    # Find the user
    result = await session.execute(
        select(User).where(User.email == data.email)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )
    
    # Update password
    user.hashed_password = hash_password(data.new_password)
    
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reset password. Please try again.",
        )
    
    return ForgotPasswordResponse(
        success=True,
        message="Password has been reset successfully. You can now log in with your new password."
    )