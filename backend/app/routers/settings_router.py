from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
import httpx
from typing import Optional
from pathlib import Path
from datetime import datetime, timezone

from app.db.database import get_session
from app.db.models import Setting, Document
from app.schemas import (
    ProviderUpdate, ProviderResponse, SettingsResponse, SettingsUpdate,
    TestConnectionRequest, DocumentResponse, DocumentListResponse,
    DocumentExpiryUpdate,
    ScraperPageResult, ScraperRunResponse, ScraperConfigResponse,
    ScraperConfigUpdate, ScraperUrlAdd, ScraperUrlRemove,
)
from app.auth import get_current_user, get_current_admin_user
from app.llm_provider import llm_provider
from app.config import (
    ACADEMIC_DIR, ADMINISTRATIVE_DIR, EDUCATIONAL_DIR,
    ALLOWED_EXTENSIONS, MAX_FILE_SIZE, RESTRICTED_EMAIL_DOMAIN,
)
from app.document_parser import extract_text

router = APIRouter(prefix="/settings", tags=["Settings"])


@router.post("/test-connection")
async def test_connection(
    request: TestConnectionRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Test connection to AI providers in real-time.
    
    Returns:
        - success: Boolean indicating if connection was successful
        - message: Status message
        - details: Additional details about the connection
    """
    
    provider = request.provider
    api_key = request.api_key
    ollama_url = request.ollama_url
    
    try:
        if provider == "openai":
            if not api_key:
                return {
                    "success": False,
                    "message": "OpenAI API key is required",
                    "details": None
                }
            
            # Test OpenAI connection
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    models = response.json()
                    model_count = len(models.get("data", []))
                    return {
                        "success": True,
                        "message": f"Connected to OpenAI successfully",
                        "details": f"Found {model_count} available models"
                    }
                else:
                    return {
                        "success": False,
                        "message": "Invalid API key or connection failed",
                        "details": f"Status code: {response.status_code}"
                    }
                    
        elif provider == "gemini":
            if not api_key:
                return {
                    "success": False,
                    "message": "Gemini API key is required",
                    "details": None
                }
            
            # Test Gemini connection
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://generativelanguage.googleapis.com/v1/models?key={api_key}",
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    models = response.json()
                    model_count = len(models.get("models", []))
                    return {
                        "success": True,
                        "message": "Connected to Gemini successfully",
                        "details": f"Found {model_count} available models"
                    }
                else:
                    return {
                        "success": False,
                        "message": "Invalid API key or connection failed",
                        "details": f"Status code: {response.status_code}"
                    }
                    
        elif provider == "ollama":
            url = ollama_url or "http://localhost:11434"
            
            # Test Ollama connection
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{url}/api/tags",
                    timeout=5.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    model_count = len(data.get("models", []))
                    return {
                        "success": True,
                        "message": "Connected to Ollama successfully",
                        "details": f"Found {model_count} model(s)"
                    }
                else:
                    return {
                        "success": False,
                        "message": "Cannot connect to Ollama",
                        "details": "Make sure Ollama is running"
                    }
        elif provider == "deepseek":
            if not api_key:
                return {"success": False, "message": "DeepSeek API key is required", "details": None}
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://api.deepseek.com/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=10.0
                )
                if response.status_code == 200:
                    model_count = len(response.json().get("data", []))
                    return {
                        "success": True,
                        "message": "Connected to DeepSeek successfully",
                        "details": f"Found {model_count} available models"
                    }
                else:
                    return {
                        "success": False,
                        "message": "Invalid API key or connection failed",
                        "details": f"Status code: {response.status_code}"
                    }
        else:
            return {
                "success": False,
                "message": "Invalid provider",
                "details": f"Provider '{provider}' is not supported"
            }
            
    except httpx.TimeoutException:
        return {
            "success": False,
            "message": "Connection timeout",
            "details": "The request timed out. Check your network or service availability."
        }
    except Exception as e:
        return {
            "success": False,
            "message": "Connection failed",
            "details": str(e)
        }


@router.get("/provider", response_model=ProviderResponse)
async def get_provider_settings(
    current_user: dict = Depends(get_current_user),
):
    """Get current AI provider configuration."""
    
    current_provider = llm_provider.get_current_provider()
    available_providers = llm_provider.get_available_providers()
    
    return ProviderResponse(
        ai_provider=current_provider,
        available_providers=available_providers,
    )



@router.get("/provider/defaults")
async def get_provider_defaults(
    current_user: dict = Depends(get_current_user),
):
    """Expose which provider defaults are configured server-side."""
    return llm_provider.get_env_defaults()

@router.put("/provider", response_model=ProviderResponse)
async def update_provider_settings(
    provider_data: ProviderUpdate,
    current_user: dict = Depends(get_current_admin_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Update AI provider configuration (Admin only).
    
    This endpoint allows switching between:
    - openai: OpenAI GPT-4
    - gemini: Google Gemini
    - ollama: Local Gemma via Ollama
    - auto: Automatic fallback selection
    """
    
    try:
        # Update provider in memory
        llm_provider.set_provider(provider_data.ai_provider)
        
        # Update in database
        result = await session.execute(
            select(Setting).order_by(Setting.updated_at.desc())
        )
        settings = result.scalar_one_or_none()
        
        if settings:
            settings.ai_provider = provider_data.ai_provider
        else:
            settings = Setting(ai_provider=provider_data.ai_provider)
            session.add(settings)
        
        await session.commit()
        
        # Get updated available providers
        available_providers = llm_provider.get_available_providers()
        
        return ProviderResponse(
            ai_provider=provider_data.ai_provider,
            available_providers=available_providers,
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating provider: {str(e)}"
        )


@router.get("/", response_model=SettingsResponse)
async def get_settings(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get all application settings."""
    
    result = await session.execute(
        select(Setting).order_by(Setting.updated_at.desc())
    )
    settings = result.scalar_one_or_none()
    
    if not settings:
        # Create default settings
        settings = Setting()
        session.add(settings)
        await session.commit()
        await session.refresh(settings)
    
    return SettingsResponse.model_validate(settings)


@router.put("/", response_model=SettingsResponse)
async def update_settings(
    settings_data: SettingsUpdate,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Update application settings and provider configuration."""
    
    result = await session.execute(
        select(Setting).order_by(Setting.updated_at.desc())
    )
    settings = result.scalar_one_or_none()
    
    if not settings:
        settings = Setting()
        session.add(settings)
    
    # Update AI provider if provided
    if settings_data.ai_provider is not None:
        settings.ai_provider = settings_data.ai_provider
        # Update the global provider
        llm_provider.set_provider(settings_data.ai_provider)
    
    await session.commit()
    await session.refresh(settings)
    
    return SettingsResponse.model_validate(settings)


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    category: str = Form(...),
    expiry_date: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Upload a document to the knowledge base.
    
    Supported formats: TXT, PDF, DOCX.
    PDF and DOCX files are automatically converted to plain text.
    
    Creates a Document record in PostgreSQL alongside the file and
    Qdrant vector index (Paper §3.4 — Automatic Document Indexing).
    """
    
    # Restrict file upload access for restricted-domain users
    user_email = current_user.get("email", "")
    if user_email.endswith(RESTRICTED_EMAIL_DOMAIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="File upload is not allowed for restricted-domain users"
        )
    
    # Validate category
    valid_categories = {"Academic", "Administrative", "Educational"}
    if category not in valid_categories:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid category. Must be one of: {', '.join(valid_categories)}"
        )
    
    # Sanitize filename to prevent path traversal
    safe_filename = Path(file.filename).name
    if not safe_filename or safe_filename.startswith('.'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename"
        )
    
    # Validate file extension
    file_ext = Path(safe_filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type '{file_ext}'. Allowed: {allowed}"
        )
    
    # Read file content to check size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File size exceeds maximum limit of {MAX_FILE_SIZE / (1024*1024):.0f}MB"
        )
    
    # Get category directory
    category_dirs = {
        "Academic": ACADEMIC_DIR,
        "Administrative": ADMINISTRATIVE_DIR,
        "Educational": EDUCATIONAL_DIR
    }
    target_dir = category_dirs[category]
    
    # Ensure directory exists
    target_dir.mkdir(parents=True, exist_ok=True)
    
    # Extract text from the document (PDF/DOCX are converted to plain text)
    try:
        extracted_text, output_filename = extract_text(safe_filename, content)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
    
    # Save extracted text as .txt file (best-effort; Vercel has read-only FS)
    file_path = target_dir / output_filename
    file_saved = False
    
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        if file_path.exists():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"File '{output_filename}' already exists in {category} category"
            )
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(extracted_text)
        file_saved = True
    except HTTPException:
        raise
    except OSError:
        # Read-only filesystem (e.g. Vercel) – skip local save
        print(f"Warning: Could not write '{output_filename}' to disk (read-only FS)")
    
    try:
        original_ext = Path(safe_filename).suffix.lower()
        converted_note = ""
        if original_ext != '.txt':
            converted_note = f" (converted from {original_ext.upper().lstrip('.')})"
        
        # Index the document in Qdrant vector store for semantic search
        chunk_count = 0
        vector_ids: list[str] = []
        try:
            from app.vector_store import index_document
            chunk_count, vector_ids = index_document(extracted_text, output_filename, category)
            print(f"Indexed '{output_filename}' in Qdrant ({chunk_count} chunks)")
        except Exception as vec_err:
            print(f"Warning: Vector indexing failed for '{output_filename}': {vec_err}")
        
        # Create Document record in PostgreSQL
        user_id = current_user.get("user_id")

        # Parse optional expiry_date
        parsed_expiry = None
        if expiry_date:
            try:
                parsed_expiry = datetime.fromisoformat(expiry_date.replace('Z', '+00:00'))
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid expiry_date format. Use ISO 8601 (e.g. 2026-06-15T00:00:00Z)"
                )

        doc_record = Document(
            filename=output_filename,
            original_filename=safe_filename,
            category=category,
            file_type=file_ext,
            file_size=len(extracted_text.encode('utf-8')),
            original_size=len(content),
            chunk_count=chunk_count,
            vector_ids=vector_ids,
            uploaded_by=user_id,
            expiry_date=parsed_expiry,
        )
        session.add(doc_record)
        await session.commit()
        await session.refresh(doc_record)
        print(f"Document record created in PostgreSQL: {doc_record.id}")
        
        return {
            "success": True,
            "message": f"File uploaded successfully to {category} category{converted_note}",
            "filename": output_filename,
            "original_filename": safe_filename,
            "category": category,
            "size": len(extracted_text.encode('utf-8')),
            "original_size": len(content),
            "chunk_count": chunk_count,
            "document_id": str(doc_record.id),
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        # Clean up if file was partially written
        if file_saved and file_path.exists():
            file_path.unlink()
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error saving file: {str(e)}"
        )


@router.get("/files")
async def list_uploaded_files(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    List all uploaded files in the knowledge base, organized by category.
    
    Queries the PostgreSQL Document table. Falls back to filesystem glob
    for any files not yet tracked in the database.
    """
    # Query all documents from PostgreSQL
    result = await session.execute(
        select(Document).order_by(Document.category, Document.filename)
    )
    db_docs = result.scalars().all()

    # Build a set of (filename, category) from DB for dedup
    db_keys: set[tuple[str, str]] = set()
    files = []
    for doc in db_docs:
        db_keys.add((doc.filename, doc.category))
        files.append(DocumentResponse.model_validate(doc).model_dump())

    # Fallback: also pick up any .txt files on disk not yet tracked in DB
    category_dirs = {
        "Academic": ACADEMIC_DIR,
        "Administrative": ADMINISTRATIVE_DIR,
        "Educational": EDUCATIONAL_DIR,
    }
    for category, dir_path in category_dirs.items():
        if not dir_path.exists():
            continue
        for file_path in sorted(dir_path.glob("*.txt")):
            if (file_path.name, category) in db_keys:
                continue
            stat = file_path.stat()
            files.append({
                "filename": file_path.name,
                "category": category,
                "size": stat.st_size,
                "modified": stat.st_mtime,
            })

    return {"files": files}


@router.get("/files/{category}/{filename}/content")
async def get_file_content(
    category: str,
    filename: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Return the text content of an uploaded knowledge-base file.
    Limited to 100 KB to avoid oversized responses.
    """
    category_dirs = {
        "Academic": ACADEMIC_DIR,
        "Administrative": ADMINISTRATIVE_DIR,
        "Educational": EDUCATIONAL_DIR,
    }
    base_dir = category_dirs.get(category)
    if not base_dir:
        raise HTTPException(status_code=400, detail="Invalid category")

    # Resolve and ensure the path stays inside the category directory
    file_path = (base_dir / filename).resolve()
    if not str(file_path).startswith(str(base_dir.resolve())):
        raise HTTPException(status_code=400, detail="Invalid filename")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    MAX_CONTENT = 100 * 1024  # 100 KB
    try:
        raw = file_path.read_text(encoding="utf-8", errors="replace")
        truncated = len(raw) > MAX_CONTENT
        content = raw[:MAX_CONTENT]
        return {"content": content, "truncated": truncated}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")


@router.delete("/files/{category}/{filename}")
async def delete_uploaded_file(
    category: str,
    filename: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Delete an uploaded file from the knowledge base.
    
    Removes the file from disk, its vectors from Qdrant, and its
    Document record from PostgreSQL.
    """
    # Restrict delete access for restricted-domain users
    user_email = current_user.get("email", "")
    if user_email.endswith(RESTRICTED_EMAIL_DOMAIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="File deletion is not allowed for restricted-domain users"
        )
    
    # Validate category
    valid_categories = {"Academic", "Administrative", "Educational"}
    if category not in valid_categories:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid category. Must be one of: {', '.join(valid_categories)}"
        )
    
    category_dirs = {
        "Academic": ACADEMIC_DIR,
        "Administrative": ADMINISTRATIVE_DIR,
        "Educational": EDUCATIONAL_DIR,
    }
    target_dir = category_dirs[category]
    
    # Sanitize filename to prevent path traversal
    safe_filename = Path(filename).name
    if not safe_filename or safe_filename.startswith('.') or '/' in filename or '\\' in filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename"
        )
    
    file_path = target_dir / safe_filename
    
    # Check DB record exists (primary source of truth)
    result = await session.execute(
        select(Document).where(
            and_(
                Document.filename == safe_filename,
                Document.category == category,
            )
        )
    )
    doc_record = result.scalar_one_or_none()
    
    if not doc_record and not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File '{safe_filename}' not found in {category} category"
        )
    
    try:
        # Remove from disk if present (may not exist on Vercel)
        if file_path.exists():
            file_path.unlink()
        
        # Remove document vectors from Qdrant
        try:
            from app.vector_store import delete_document
            delete_document(safe_filename, category)
            print(f"Removed vectors for '{safe_filename}' from Qdrant")
        except Exception as vec_err:
            print(f"Warning: Vector deletion failed for '{safe_filename}': {vec_err}")
        
        # Remove Document record from PostgreSQL
        if doc_record:
            await session.delete(doc_record)
            await session.commit()
            print(f"Deleted Document record from PostgreSQL: {doc_record.id}")
        
        return {
            "success": True,
            "message": f"File '{safe_filename}' deleted from {category} category",
            "filename": safe_filename,
            "category": category,
        }
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting file: {str(e)}"
        )


# -----------------------------------------------------------------------
# Document Expiry Management
# -----------------------------------------------------------------------

@router.patch("/files/{document_id}/expiry", response_model=DocumentResponse)
async def update_document_expiry(
    document_id: str,
    body: DocumentExpiryUpdate,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Set or remove expiry date on a document.

    - Send `{ "expiry_date": "2026-06-15T00:00:00Z" }` to set expiry.
    - Send `{ "expiry_date": null }` to remove expiry (never expires).
    """
    user_email = current_user.get("email", "")
    if user_email.endswith(RESTRICTED_EMAIL_DOMAIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Expiry management is not allowed for restricted-domain users",
        )

    result = await session.execute(
        select(Document).where(Document.id == document_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    doc.expiry_date = body.expiry_date
    # Refresh cached `is_expired` flag
    if body.expiry_date is None:
        doc.is_expired = False
    else:
        doc.is_expired = body.expiry_date <= datetime.now(timezone.utc)

    await session.commit()
    await session.refresh(doc)
    return DocumentResponse.model_validate(doc)


@router.get("/files/expired", response_model=DocumentListResponse)
async def list_expired_documents(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """List all documents whose expiry_date has passed."""
    now = datetime.now(timezone.utc)
    result = await session.execute(
        select(Document).where(Document.expiry_date <= now).order_by(Document.expiry_date)
    )
    docs = result.scalars().all()
    return {"files": [DocumentResponse.model_validate(d) for d in docs]}


@router.post("/files/refresh-expiry")
async def refresh_expiry_flags(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Bulk-refresh the `is_expired` flag on every document.
    Called on app startup or manually from the Settings UI.
    """
    now = datetime.now(timezone.utc)
    result = await session.execute(select(Document))
    docs = result.scalars().all()
    updated = 0
    for doc in docs:
        should_be_expired = doc.expiry_date is not None and doc.expiry_date <= now
        if doc.is_expired != should_be_expired:
            doc.is_expired = should_be_expired
            updated += 1
    if updated:
        await session.commit()
    return {"success": True, "updated": updated, "total": len(docs)}


# -----------------------------------------------------------------------
# Web Scraper — Official College Website
# -----------------------------------------------------------------------

@router.get("/scraper/config", response_model=ScraperConfigResponse)
async def get_scraper_config(
    current_user: dict = Depends(get_current_user),
):
    """Return the current list of target URLs for the web scraper."""
    try:
        from app.web_scraper import scraper_config
    except ImportError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Web scraper module unavailable: {e}",
        )
    return ScraperConfigResponse(urls=scraper_config.get_urls())


@router.put("/scraper/config", response_model=ScraperConfigResponse)
async def update_scraper_config(
    body: ScraperConfigUpdate,
    current_user: dict = Depends(get_current_admin_user),
):
    """Replace the full URL list (admin only)."""
    from app.web_scraper import scraper_config
    scraper_config.set_urls(body.urls)
    return ScraperConfigResponse(urls=scraper_config.get_urls())


@router.post("/scraper/config/add", response_model=ScraperConfigResponse)
async def add_scraper_url(
    body: ScraperUrlAdd,
    current_user: dict = Depends(get_current_user),
):
    """Add a single URL to the scraper target list."""
    user_email = current_user.get("email", "")
    if user_email.endswith(RESTRICTED_EMAIL_DOMAIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Scraper management is not allowed for restricted-domain users",
        )
    from app.web_scraper import scraper_config
    added = scraper_config.add_url(body.url)
    if not added:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="URL already exists or is invalid",
        )
    return ScraperConfigResponse(urls=scraper_config.get_urls())


@router.post("/scraper/config/remove", response_model=ScraperConfigResponse)
async def remove_scraper_url(
    body: ScraperUrlRemove,
    current_user: dict = Depends(get_current_user),
):
    """Remove a single URL from the scraper target list."""
    user_email = current_user.get("email", "")
    if user_email.endswith(RESTRICTED_EMAIL_DOMAIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Scraper management is not allowed for restricted-domain users",
        )
    from app.web_scraper import scraper_config
    removed = scraper_config.remove_url(body.url)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="URL not found in the target list",
        )
    return ScraperConfigResponse(urls=scraper_config.get_urls())


@router.post("/scraper/scrape", response_model=ScraperRunResponse)
async def trigger_scrape(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Trigger an immediate scrape of all configured URLs.

    Scrapes each page, saves .txt files to the data directory,
    indexes content in Qdrant, and creates Document records in PostgreSQL.
    Returns a ScraperRun summary.
    """
    user_email = current_user.get("email", "")
    if user_email.endswith(RESTRICTED_EMAIL_DOMAIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Scraper is not allowed for restricted-domain users",
        )

    from app.web_scraper import scraper_config, run_scrape
    from app.db.models import ScraperRun

    urls = scraper_config.get_urls()
    user_id = current_user.get("user_id")

    # Create run record
    run = ScraperRun(
        pages_attempted=len(urls),
        triggered_by=user_id,
    )
    session.add(run)
    await session.flush()

    try:
        results = await run_scrape(urls)

        docs_created = 0
        errors: list[str] = []
        total_chunks = 0
        succeeded = 0
        failed = 0

        for pr in results:
            if pr.success:
                succeeded += 1
                total_chunks += pr.chunks

                # Create / update Document record in PostgreSQL
                existing = await session.execute(
                    select(Document).where(
                        and_(
                            Document.filename == pr.filename,
                            Document.category == pr.category,
                        )
                    )
                )
                doc = existing.scalar_one_or_none()
                if doc:
                    # Update existing record
                    doc.file_size = pr.text_length
                    doc.chunk_count = pr.chunks
                    doc.updated_at = datetime.now(timezone.utc)
                else:
                    # Create new record
                    doc = Document(
                        filename=pr.filename,
                        original_filename=pr.url,
                        category=pr.category,
                        file_type=".txt",
                        file_size=pr.text_length,
                        chunk_count=pr.chunks,
                        vector_ids=[],
                        uploaded_by=user_id,
                    )
                    session.add(doc)
                    docs_created += 1

                if pr.error:
                    errors.append(f"{pr.url}: {pr.error}")
            else:
                failed += 1
                errors.append(f"{pr.url}: {pr.error}")

        run.finished_at = datetime.now(timezone.utc)
        run.status = "completed"
        run.pages_succeeded = succeeded
        run.pages_failed = failed
        run.chunks_indexed = total_chunks
        run.documents_created = docs_created
        run.errors = errors

        await session.commit()
        await session.refresh(run)
        return ScraperRunResponse.model_validate(run)

    except Exception as e:
        run.finished_at = datetime.now(timezone.utc)
        run.status = "failed"
        run.errors = [str(e)]
        await session.commit()
        await session.refresh(run)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Scraper failed: {e}",
        )


@router.get("/scraper/status", response_model=list[ScraperRunResponse])
async def get_scraper_status(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Return the last 10 scraper runs (most recent first)."""
    from app.db.models import ScraperRun

    result = await session.execute(
        select(ScraperRun).order_by(ScraperRun.started_at.desc()).limit(10)
    )
    runs = result.scalars().all()
    return [ScraperRunResponse.model_validate(r) for r in runs]
