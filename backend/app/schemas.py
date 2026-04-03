from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List
from datetime import datetime
from uuid import UUID


# Auth Schemas
class UserRegister(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    email: str
    username: str
    is_active: bool
    is_admin: bool
    created_at: datetime
    
    @field_validator('id', mode='before')
    @classmethod
    def convert_uuid_to_str(cls, v):
        if isinstance(v, UUID):
            return str(v)
        return v
    
    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# Chat Schemas
class ChatCreate(BaseModel):
    title: Optional[str] = "New Chat"


class ChatResponse(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    
    @field_validator('id', mode='before')
    @classmethod
    def convert_uuid_to_str(cls, v):
        if isinstance(v, UUID):
            return str(v)
        return v
    
    class Config:
        from_attributes = True


class MessageCreate(BaseModel):
    chat_id: Optional[str] = None
    message: str = Field(..., min_length=1, max_length=5000)


class MessageResponse(BaseModel):
    id: str
    chat_id: str
    human: str
    bot: str
    created_at: datetime
    
    @field_validator('id', 'chat_id', mode='before')
    @classmethod
    def convert_uuid_to_str(cls, v):
        if isinstance(v, UUID):
            return str(v)
        return v
    
    class Config:
        from_attributes = True


class ChatWithMessages(BaseModel):
    id: str
    title: str
    updated_at: datetime
    messages: list[MessageResponse]
    
    @field_validator('id', mode='before')
    @classmethod
    def convert_uuid_to_str(cls, v):
        if isinstance(v, UUID):
            return str(v)
        return v
    
    class Config:
        from_attributes = True


class ChatRename(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)


# Settings Schemas
class ProviderUpdate(BaseModel):
    ai_provider: str = Field(..., pattern="^(openai|gemini|ollama|deepseek|auto)$")


class ProviderResponse(BaseModel):
    ai_provider: str
    available_providers: dict[str, bool]


class SettingsResponse(BaseModel):
    id: int
    ai_provider: str
    updated_at: datetime
    
    class Config:
        from_attributes = True


class SettingsUpdate(BaseModel):
    ai_provider: Optional[str] = Field(None, pattern="^(openai|gemini|ollama|deepseek|auto)$")


class TestConnectionRequest(BaseModel):
    """Test connection request schema."""
    provider: str
    api_key: Optional[str] = None
    ollama_url: Optional[str] = None


# OTP Schemas
class SendOTPRequest(BaseModel):
    """Request to send OTP."""
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)


class SendOTPResponse(BaseModel):
    """Response after sending OTP."""
    success: bool
    message: str


class VerifyOTPRequest(BaseModel):
    """Request to verify OTP."""
    email: EmailStr
    otp: str = Field(..., min_length=6, max_length=6)


class VerifyOTPResponse(BaseModel):
    """Response after verifying OTP."""
    success: bool
    message: str


# Document Schemas
class DocumentResponse(BaseModel):
    """Response schema for a knowledge-base document."""
    id: str
    filename: str
    original_filename: Optional[str] = None
    category: str
    file_type: str
    file_size: int
    original_size: Optional[int] = None
    chunk_count: int
    vector_ids: List[str] = []
    uploaded_by: Optional[str] = None
    upload_date: datetime
    updated_at: datetime
    expiry_date: Optional[datetime] = None
    is_expired: bool = False

    @field_validator('id', 'uploaded_by', mode='before')
    @classmethod
    def convert_uuid_to_str(cls, v):
        if isinstance(v, UUID):
            return str(v)
        if v is None:
            return v
        return v

    class Config:
        from_attributes = True


class DocumentListResponse(BaseModel):
    """Response schema for list of documents."""
    files: List[DocumentResponse]


# Forgot Password Schemas
class ForgotPasswordRequest(BaseModel):
    """Request to send password reset OTP."""
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    """Response after sending password reset OTP."""
    success: bool
    message: str


class VerifyResetOTPRequest(BaseModel):
    """Request to verify password reset OTP."""
    email: EmailStr
    otp: str = Field(..., min_length=6, max_length=6)


class ResetPasswordRequest(BaseModel):
    """Request to reset password after OTP verification."""
    email: EmailStr
    otp: str = Field(..., min_length=6, max_length=6)
    new_password: str = Field(..., min_length=6)


class DocumentExpiryUpdate(BaseModel):
    """Request schema for updating document expiry date."""
    expiry_date: Optional[datetime] = None  # None = remove expiry (never expires)


# ── Web Scraper Schemas ────────────────────────────────────────────

class ScraperPageResult(BaseModel):
    """Result of scraping a single page."""
    url: str
    success: bool
    category: str = ""
    filename: str = ""
    text_length: int = 0
    chunks: int = 0
    error: str = ""


class ScraperRunResponse(BaseModel):
    """Response for a scraper run."""
    id: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    status: str
    pages_attempted: int
    pages_succeeded: int
    pages_failed: int
    chunks_indexed: int
    documents_created: int
    errors: List[str] = []

    @field_validator('id', mode='before')
    @classmethod
    def convert_uuid_to_str(cls, v):
        if isinstance(v, UUID):
            return str(v)
        return v

    class Config:
        from_attributes = True


class ScraperConfigResponse(BaseModel):
    """Response for scraper configuration."""
    urls: List[str]


class ScraperConfigUpdate(BaseModel):
    """Request to update scraper target URLs."""
    urls: List[str] = Field(..., min_length=1)


class ScraperUrlAdd(BaseModel):
    """Request to add a single URL."""
    url: str = Field(..., min_length=8)


class ScraperUrlRemove(BaseModel):
    """Request to remove a single URL."""
    url: str
