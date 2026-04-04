import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Text, ForeignKey, Boolean, Integer, JSON
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship
from app.db.database import Base


class User(Base):
    """User model for authentication."""
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    permissions = Column(ARRAY(String), nullable=False, default=[])
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    chats = relationship("Chat", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User {self.username}>"


class Chat(Base):
    """Chat session model."""
    __tablename__ = "chats"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), default="New Chat")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    archived_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="chats")
    messages = relationship("Message", back_populates="chat", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Chat {self.id}: {self.title}>"


class Message(Base):
    """Message model for chat conversations."""
    __tablename__ = "messages"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chat_id = Column(UUID(as_uuid=True), ForeignKey("chats.id", ondelete="CASCADE"), nullable=False)
    human = Column(Text, nullable=False)  # User's message
    bot = Column(Text, nullable=False)  # Bot's response
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    chat = relationship("Chat", back_populates="messages")
    
    def __repr__(self):
        return f"<Message {self.id}>"


class MessageFeedback(Base):
    """User feedback for bot responses."""
    __tablename__ = "message_feedback"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chat_id = Column(UUID(as_uuid=True), ForeignKey("chats.id", ondelete="SET NULL"), nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    feedback_type = Column(String(20), nullable=False)  # positive | negative
    reason = Column(Text, nullable=True)
    user_message = Column(Text, nullable=False)
    bot_message = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<MessageFeedback {self.id} {self.feedback_type}>"


class GoldenExample(Base):
    """Admin-curated ideal responses derived from feedback."""
    __tablename__ = "golden_examples"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    feedback_id = Column(UUID(as_uuid=True), ForeignKey("message_feedback.id", ondelete="SET NULL"), nullable=True)
    source_type = Column(String(20), nullable=False, default="manual")  # positive | negative | manual
    original_query = Column(Text, nullable=False)
    original_response = Column(Text, nullable=False)
    golden_response = Column(Text, nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<GoldenExample {self.id} {self.source_type}>"


class Setting(Base):
    """Application settings model."""
    __tablename__ = "settings"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    ai_provider = Column(String(50), default="auto")  # openai, gemini, ollama, deepseek, auto
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    def __repr__(self):
        return f"<Setting id={self.id} provider={self.ai_provider}>"


class Document(Base):
    """
    Knowledge-base document metadata (Paper §3.4 — Automatic Document Indexing).

    Tracks every file uploaded to the knowledge base alongside the vector
    IDs stored in Qdrant so we can reconcile the two stores.
    """
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String(255), nullable=False, index=True)
    original_filename = Column(String(255), nullable=True)
    category = Column(String(50), nullable=False, index=True)  # Academic / Administrative / Educational
    file_type = Column(String(10), nullable=False)              # .txt, .pdf, .docx
    file_size = Column(Integer, nullable=False, default=0)      # bytes (extracted text)
    original_size = Column(Integer, nullable=True)               # bytes (raw upload)
    chunk_count = Column(Integer, nullable=False, default=0)
    vector_ids = Column(ARRAY(String), nullable=False, default=[])  # Qdrant point UUIDs
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    upload_date = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Document expiry management
    expiry_date = Column(DateTime(timezone=True), nullable=True)   # NULL = never expires
    is_expired = Column(Boolean, default=False, nullable=False)    # Cached expiry flag

    # Relationships
    uploader = relationship("User", foreign_keys=[uploaded_by])

    def __repr__(self):
        return f"<Document {self.filename} [{self.category}]>"


class ScraperRun(Base):
    """
    Web scraper execution log.

    Tracks each time the scraper runs — how many pages were attempted,
    how many succeeded, total chunks indexed, and any errors.
    """
    __tablename__ = "scraper_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    finished_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), nullable=False, default="running")  # running / completed / failed
    pages_attempted = Column(Integer, nullable=False, default=0)
    pages_succeeded = Column(Integer, nullable=False, default=0)
    pages_failed = Column(Integer, nullable=False, default=0)
    chunks_indexed = Column(Integer, nullable=False, default=0)
    documents_created = Column(Integer, nullable=False, default=0)
    errors = Column(ARRAY(String), nullable=False, default=[])
    triggered_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationship
    user = relationship("User", foreign_keys=[triggered_by])

    def __repr__(self):
        return f"<ScraperRun {self.id} [{self.status}]>"


class OTPToken(Base):
    """
    OTP tokens stored in PostgreSQL for serverless compatibility.

    Replaces in-memory OTP dicts that are lost across Vercel cold starts.
    """
    __tablename__ = "otp_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), nullable=False, index=True)
    otp = Column(String(10), nullable=False)
    purpose = Column(String(20), nullable=False)  # 'registration' or 'password_reset'
    username = Column(String(100), nullable=True)
    hashed_password = Column(String(255), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<OTPToken {self.email} [{self.purpose}]>"


class Integration(Base):
    """External integration configuration record."""
    __tablename__ = "integrations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_name = Column(String(100), nullable=False, index=True)
    auth_type = Column(String(50), nullable=False, default="api_key")
    config = Column(JSON, nullable=False, default={})
    is_active = Column(Boolean, nullable=False, default=True)
    last_sync_status = Column(String(30), nullable=True)
    last_sync_error = Column(Text, nullable=True)
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<Integration {self.service_name} active={self.is_active}>"
