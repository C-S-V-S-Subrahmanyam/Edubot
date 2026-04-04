"""
EduBot+ Backend - Multi-Model AI Chatbot

Main FastAPI application with LangGraph agent workflow.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from app.config import CORS_ORIGINS, DEBUG
from app.db.database import init_db, AsyncSessionLocal, engine
from app.db.models import Document, User
from app.routers import auth_router, chat_router, settings_router, feedback_router, integrations_router
from app.learning_intelligence import learning_intelligence

from sqlalchemy import select, text


async def _startup_seed_and_sync():
    """Seed Qdrant, sync document metadata to PostgreSQL, and refresh expiry flags."""
    # 1. Initialize Qdrant vector store
    print("📐 Initializing Qdrant vector store...")
    try:
        from app.vector_store import ensure_collection, seed_existing_documents
        ensure_collection()
        seed_existing_documents()
        print("✅ Qdrant vector store ready")
    except Exception as e:
        print(f"⚠️ Qdrant initialization failed (non-fatal): {e}")

    # 2. Sync data/ files into PostgreSQL Document table
    print("📄 Syncing document metadata to PostgreSQL...")
    try:
        from app.config import ACADEMIC_DIR, ADMINISTRATIVE_DIR, EDUCATIONAL_DIR
        from sqlalchemy import and_

        async with AsyncSessionLocal() as session:
            dirs = {
                "Academic": ACADEMIC_DIR,
                "Administrative": ADMINISTRATIVE_DIR,
                "Educational": EDUCATIONAL_DIR,
            }
            created = 0
            for category, dir_path in dirs.items():
                if not dir_path.exists():
                    continue
                for txt_file in sorted(dir_path.glob("*.txt")):
                    result = await session.execute(
                        select(Document).where(
                            and_(
                                Document.filename == txt_file.name,
                                Document.category == category,
                            )
                        )
                    )
                    if result.scalar_one_or_none():
                        continue
                    stat = txt_file.stat()
                    doc = Document(
                        filename=txt_file.name,
                        original_filename=txt_file.name,
                        category=category,
                        file_type=".txt",
                        file_size=stat.st_size,
                        chunk_count=0,
                        vector_ids=[],
                    )
                    session.add(doc)
                    created += 1
            if created:
                await session.commit()
            print(f"✅ Document metadata synced ({created} new records)")
    except Exception as e:
        print(f"⚠️ Document metadata sync failed (non-fatal): {e}")

    # 3. Refresh document expiry flags
    print("⏰ Refreshing document expiry flags...")
    try:
        async with AsyncSessionLocal() as session:
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
            print(f"✅ Expiry flags refreshed ({updated} updated out of {len(docs)})")
    except Exception as e:
        print(f"⚠️ Expiry flag refresh failed (non-fatal): {e}")


async def _bootstrap_admin_user() -> None:
    """Ensure the known bootstrap admin user has admin privileges."""
    print("👤 Ensuring bootstrap admin access...")
    try:
        from app.config import ADMIN_OVERRIDE_USERNAMES

        if not ADMIN_OVERRIDE_USERNAMES:
            print("ℹ️ No admin override usernames configured")
            return

        async with AsyncSessionLocal() as session:
            result = await session.execute(select(User))
            users = result.scalars().all()

            updated = 0
            for user in users:
                uname = (user.username or "").strip().lower()
                email_prefix = (user.email or "").split("@")[0].lower() if user.email else ""
                if uname in ADMIN_OVERRIDE_USERNAMES or email_prefix in ADMIN_OVERRIDE_USERNAMES:
                    changed = False
                    if not user.is_admin:
                        user.is_admin = True
                        changed = True
                    perms = set(user.permissions or [])
                    required = {"feedback.manage", "integration.manage"}
                    if not required.issubset(perms):
                        user.permissions = sorted(perms.union(required))
                        changed = True
                    if changed:
                        updated += 1

            if updated:
                await session.commit()
                print(f"✅ Bootstrap admin updated for {updated} user(s)")
            else:
                print("✅ Bootstrap admin check complete (no changes needed)")
    except Exception as e:
        print(f"⚠️ Bootstrap admin update failed (non-fatal): {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    print("🚀 Starting EduBot+ Backend...")
    print("📦 Initializing database...")
    await init_db()
    print("✅ Database initialized")

    await _startup_seed_and_sync()
    await _bootstrap_admin_user()

    print("🧠 Initializing sentiment + recommendation models...")
    try:
        learning_intelligence.initialize()
        metrics = learning_intelligence.get_metrics()
        print(
            "✅ Learning models ready "
            f"(sentiment_accuracy={metrics.get('sentiment_accuracy')}, topics={metrics.get('topic_count')})"
        )
    except Exception as e:
        print(f"⚠️ Learning model initialization failed (non-fatal): {e}")

    print("🤖 LangGraph Agent ready")
    print("💬 Multi-model chatbot system active")

    yield

    print("👋 Shutting down EduBot+ Backend...")


# Create FastAPI app
app = FastAPI(
    title="EduBot+ API",
    description="Multi-Model AI Chatbot with LangGraph Agent Workflow",
    version="1.0.0",
    lifespan=lifespan,
    debug=DEBUG,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router.router, prefix="/api")
app.include_router(chat_router.router, prefix="/api")
app.include_router(settings_router.router, prefix="/api")
app.include_router(feedback_router.router, prefix="/api")
app.include_router(integrations_router.router, prefix="/api")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "EduBot+ API - Multi-Model AI Chatbot",
        "version": "1.0.0",
        "docs": "/docs",
        "agent": "LangGraph Agent",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint — verifies database connectivity."""
    db_status = "disconnected"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception:
        pass
    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "agent": "LangGraph Agent",
        "database": db_status,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=DEBUG,
    )
