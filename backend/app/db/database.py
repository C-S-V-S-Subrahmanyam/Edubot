from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
import os
import ssl
from app.config import DATABASE_URL

# Remove query parameters from URL that asyncpg doesn't support in URL
clean_url = DATABASE_URL.split('?')[0]

# Build engine connect_args based on DATABASE_SSL env var
# Set DATABASE_SSL=false to disable SSL (e.g., for local dev)
connect_args = {}
if os.getenv("DATABASE_SSL", "true").lower() != "false":
    ssl_context = ssl.create_default_context()
    connect_args["ssl"] = ssl_context

# Cloud poolers (for example Neon pooler) can terminate prepared statements
# and long-idle sockets. Disable statement cache and add TCP keepalive.
connect_args["statement_cache_size"] = int(os.getenv("DB_STATEMENT_CACHE_SIZE", "0"))
connect_args["command_timeout"] = float(os.getenv("DB_COMMAND_TIMEOUT", "30"))
connect_args["server_settings"] = {"application_name": os.getenv("DB_APP_NAME", "edubot")}

# PostgreSQL async engine with connection pooling
engine = create_async_engine(
    clean_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    # Recycle aggressively to reduce stale pool connections on cloud DBs.
    pool_recycle=int(os.getenv("DB_POOL_RECYCLE", "300")),
    pool_use_lifo=True,
    connect_args=connect_args,
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Base class for models
Base = declarative_base()


async def get_session() -> AsyncSession:
    """Dependency for FastAPI routes to get database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """Initialize database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Run lightweight column migrations for existing tables
    async with engine.begin() as conn:
        await _migrate_columns(conn)


async def _migrate_columns(conn):
    """Add missing columns to existing tables (idempotent)."""
    migrations = [
        # Document expiry management columns
        (
            "documents", "expiry_date",
            "ALTER TABLE documents ADD COLUMN expiry_date TIMESTAMPTZ"
        ),
        (
            "documents", "is_expired",
            "ALTER TABLE documents ADD COLUMN is_expired BOOLEAN NOT NULL DEFAULT FALSE"
        ),
        (
            "users", "permissions",
            "ALTER TABLE users ADD COLUMN permissions TEXT[] NOT NULL DEFAULT '{}'"
        ),
    ]
    from sqlalchemy import text
    for table, column, ddl in migrations:
        result = await conn.execute(text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :table AND column_name = :column"
        ), {"table": table, "column": column})
        if result.fetchone() is None:
            await conn.execute(text(ddl))
            print(f"  ✅ Added column {table}.{column}")
