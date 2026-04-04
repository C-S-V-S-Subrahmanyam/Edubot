import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, require_permission
from app.db.database import get_session
from app.db.models import Integration, IntegrationSyncLog
from app.schemas import (
    IntegrationCreate,
    IntegrationUpdate,
    IntegrationResponse,
    IntegrationTestRequest,
    IntegrationSyncLogResponse,
    IntegrationSyncRunResponse,
)

router = APIRouter(prefix="/integrations", tags=["Integrations"])


def _extract_base_url(config: dict) -> str | None:
    base_url = config.get("base_url")
    if isinstance(base_url, str) and base_url.strip():
        return base_url.strip()
    return None


@router.get("/", response_model=list[IntegrationResponse])
async def list_integrations(
    current_user: dict = Depends(require_permission("integration.manage")),
    session: AsyncSession = Depends(get_session),
    limit: int = 50,
    offset: int = 0,
):
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="limit must be between 1 and 200")
    if offset < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="offset must be >= 0")

    result = await session.execute(
        select(Integration)
        .order_by(Integration.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = result.scalars().all()
    return [IntegrationResponse.model_validate(r) for r in rows]


@router.post("/", response_model=IntegrationResponse, status_code=status.HTTP_201_CREATED)
async def create_integration(
    payload: IntegrationCreate,
    current_user: dict = Depends(require_permission("integration.manage")),
    session: AsyncSession = Depends(get_session),
):
    row = Integration(
        service_name=payload.service_name,
        auth_type=payload.auth_type,
        config=payload.config,
        is_active=payload.is_active,
        created_by=uuid.UUID(current_user["user_id"]),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return IntegrationResponse.model_validate(row)


@router.patch("/{integration_id}", response_model=IntegrationResponse)
async def update_integration(
    integration_id: str,
    payload: IntegrationUpdate,
    current_user: dict = Depends(require_permission("integration.manage")),
    session: AsyncSession = Depends(get_session),
):
    try:
        itg_uuid = uuid.UUID(integration_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid integration_id") from e

    result = await session.execute(select(Integration).where(Integration.id == itg_uuid))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")

    if payload.service_name is not None:
        row.service_name = payload.service_name
    if payload.auth_type is not None:
        row.auth_type = payload.auth_type
    if payload.config is not None:
        row.config = payload.config
    if payload.is_active is not None:
        row.is_active = payload.is_active

    await session.commit()
    await session.refresh(row)
    return IntegrationResponse.model_validate(row)


@router.delete("/{integration_id}")
async def delete_integration(
    integration_id: str,
    current_user: dict = Depends(require_permission("integration.manage")),
    session: AsyncSession = Depends(get_session),
):
    try:
        itg_uuid = uuid.UUID(integration_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid integration_id") from e

    result = await session.execute(select(Integration).where(Integration.id == itg_uuid))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")

    await session.delete(row)
    await session.commit()
    return {"success": True, "message": "Integration deleted"}


@router.post("/test-connection")
async def test_integration_connection(
    payload: IntegrationTestRequest,
    current_user: dict = Depends(require_permission("integration.manage")),
):
    """Basic connectivity check for integration endpoint."""
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(payload.base_url)
        ok = 200 <= resp.status_code < 400
        return {
            "success": ok,
            "status_code": resp.status_code,
            "message": "Connection successful" if ok else "Connection returned non-success status",
        }
    except Exception as e:
        return {
            "success": False,
            "message": "Connection failed",
            "details": str(e),
        }


@router.post("/{integration_id}/sync", response_model=IntegrationSyncRunResponse)
async def run_integration_sync(
    integration_id: str,
    current_user: dict = Depends(require_permission("integration.manage")),
    session: AsyncSession = Depends(get_session),
):
    try:
        itg_uuid = uuid.UUID(integration_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid integration_id") from e

    result = await session.execute(select(Integration).where(Integration.id == itg_uuid))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")

    base_url = _extract_base_url(row.config or {})
    if not base_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Integration config.base_url is required")

    log = IntegrationSyncLog(
        integration_id=row.id,
        status="running",
        triggered_by=uuid.UUID(current_user["user_id"]),
    )
    session.add(log)
    await session.flush()

    success = False
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.get(base_url)
        success = 200 <= resp.status_code < 400

        log.status = "success" if success else "failed"
        log.http_status = resp.status_code
        log.message = "Sync probe succeeded" if success else "Sync probe returned non-success status"
        log.finished_at = datetime.now(timezone.utc)

        row.last_sync_status = log.status
        row.last_sync_error = None if success else log.message
        row.last_synced_at = log.finished_at
        await session.commit()
        await session.refresh(log)
        return IntegrationSyncRunResponse(success=success, log=IntegrationSyncLogResponse.model_validate(log))
    except Exception as e:
        log.status = "failed"
        log.message = f"Sync probe failed: {str(e)}"
        log.finished_at = datetime.now(timezone.utc)
        row.last_sync_status = "failed"
        row.last_sync_error = log.message
        row.last_synced_at = log.finished_at
        await session.commit()
        await session.refresh(log)
        return IntegrationSyncRunResponse(success=False, log=IntegrationSyncLogResponse.model_validate(log))


@router.get("/{integration_id}/sync-history", response_model=list[IntegrationSyncLogResponse])
async def get_integration_sync_history(
    integration_id: str,
    current_user: dict = Depends(require_permission("integration.manage")),
    session: AsyncSession = Depends(get_session),
    limit: int = 20,
    offset: int = 0,
):
    try:
        itg_uuid = uuid.UUID(integration_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid integration_id") from e

    if limit < 1 or limit > 200:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="limit must be between 1 and 200")
    if offset < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="offset must be >= 0")

    result = await session.execute(
        select(IntegrationSyncLog)
        .where(IntegrationSyncLog.integration_id == itg_uuid)
        .order_by(IntegrationSyncLog.started_at.desc())
        .limit(limit)
        .offset(offset)
    )
    logs = result.scalars().all()
    return [IntegrationSyncLogResponse.model_validate(item) for item in logs]
