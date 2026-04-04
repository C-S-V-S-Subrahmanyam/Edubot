import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.database import get_session
from app.db.models import MessageFeedback, GoldenExample
from app.schemas import (
    FeedbackCreate,
    FeedbackResponse,
    FeedbackStatsResponse,
    FeedbackStatusUpdate,
    FeedbackTaxonomyResponse,
    GoldenExampleCreate,
    GoldenExampleResponse,
    GoldenExampleUpdate,
)
from app.auth import get_current_user, require_permission

router = APIRouter(prefix="/feedback", tags=["Feedback"])

FEEDBACK_REASON_CATALOG = {
    "positive": [
        "Accurate answer",
        "Clear explanation",
        "Helpful step-by-step guidance",
        "Good recommendation",
        "Fast response",
    ],
    "negative": [
        "Incorrect information",
        "Answer too generic",
        "Missing important details",
        "Not grounded in backend data",
        "Hard to understand",
        "Irrelevant recommendation",
    ],
}

FEEDBACK_WORKFLOW_TRANSITIONS = {
    "pending": ["triaged", "dismissed"],
    "triaged": ["in_review", "dismissed"],
    "in_review": ["actioned", "dismissed"],
    "actioned": ["resolved", "in_review"],
    "resolved": ["resolved"],
    "reviewed": ["reviewed"],  # backward compatibility with existing rows
    "dismissed": ["dismissed"],
}


def _normalize_reason(reason: str | None) -> str | None:
    if reason is None:
        return None
    cleaned = reason.strip()
    return cleaned or None


def _is_valid_reason(feedback_type: str, reason: str | None) -> bool:
    if not reason:
        return True
    allowed = FEEDBACK_REASON_CATALOG.get(feedback_type, [])
    return reason in allowed or reason.lower().startswith("other:")


@router.post("/", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
async def create_feedback(
    payload: FeedbackCreate,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Create feedback entry for an assistant response."""
    chat_id = None
    if payload.chat_id:
        try:
            chat_id = uuid.UUID(payload.chat_id)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid chat_id format",
            ) from e

    normalized_reason = _normalize_reason(payload.reason)
    if not _is_valid_reason(payload.feedback_type, normalized_reason):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid feedback reason. Use catalog values or prefix custom reason with 'Other:'.",
        )

    feedback = MessageFeedback(
        chat_id=chat_id,
        user_id=uuid.UUID(current_user["user_id"]),
        feedback_type=payload.feedback_type,
        reason=normalized_reason,
        user_message=payload.user_message,
        bot_message=payload.bot_message,
        status="pending",
    )
    session.add(feedback)
    await session.commit()
    await session.refresh(feedback)
    return FeedbackResponse.model_validate(feedback)


@router.get("/taxonomy", response_model=FeedbackTaxonomyResponse)
async def get_feedback_taxonomy(
    current_user: dict = Depends(get_current_user),
):
    """Provide reason catalog and workflow statuses for frontend feedback UI."""
    statuses = list(FEEDBACK_WORKFLOW_TRANSITIONS.keys())
    return FeedbackTaxonomyResponse(
        reasons=FEEDBACK_REASON_CATALOG,
        statuses=statuses,
        transitions=FEEDBACK_WORKFLOW_TRANSITIONS,
    )


@router.get("/stats", response_model=FeedbackStatsResponse)
async def get_feedback_stats(
    current_user: dict = Depends(require_permission("feedback.manage")),
    session: AsyncSession = Depends(get_session),
):
    """Simple aggregate stats for feedback dashboard."""
    result = await session.execute(select(MessageFeedback))
    rows = result.scalars().all()

    total = len(rows)
    positive = sum(1 for r in rows if r.feedback_type == "positive")
    negative = sum(1 for r in rows if r.feedback_type == "negative")
    pending = sum(1 for r in rows if r.status == "pending")
    in_review = sum(1 for r in rows if r.status in {"triaged", "in_review", "actioned"})
    resolved = sum(1 for r in rows if r.status in {"resolved", "reviewed"})
    dismissed = sum(1 for r in rows if r.status == "dismissed")

    return FeedbackStatsResponse(
        total_feedback=total,
        positive_feedback=positive,
        negative_feedback=negative,
        pending_feedback=pending,
        in_review_feedback=in_review,
        resolved_feedback=resolved,
        dismissed_feedback=dismissed,
    )


@router.get("/", response_model=list[FeedbackResponse])
async def list_feedback(
    current_user: dict = Depends(require_permission("feedback.manage")),
    session: AsyncSession = Depends(get_session),
    limit: int = 50,
    offset: int = 0,
):
    """List feedback items for admin review."""
    if limit < 1 or limit > 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="limit must be between 1 and 200",
        )
    if offset < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="offset must be >= 0",
        )

    result = await session.execute(
        select(MessageFeedback)
        .order_by(MessageFeedback.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = result.scalars().all()
    return [FeedbackResponse.model_validate(r) for r in rows]


@router.patch("/{feedback_id}/status", response_model=FeedbackResponse)
async def update_feedback_status(
    feedback_id: str,
    payload: FeedbackStatusUpdate,
    current_user: dict = Depends(require_permission("feedback.manage")),
    session: AsyncSession = Depends(get_session),
):
    """Update review status for a feedback item."""
    try:
        fb_uuid = uuid.UUID(feedback_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid feedback_id") from e

    result = await session.execute(select(MessageFeedback).where(MessageFeedback.id == fb_uuid))
    feedback = result.scalar_one_or_none()
    if feedback is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feedback not found")

    current_status = feedback.status or "pending"
    allowed_next = FEEDBACK_WORKFLOW_TRANSITIONS.get(current_status, [])
    if payload.status not in allowed_next:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid status transition from '{current_status}' to '{payload.status}'. "
                f"Allowed: {allowed_next}"
            ),
        )

    feedback.status = payload.status
    await session.commit()
    await session.refresh(feedback)
    return FeedbackResponse.model_validate(feedback)


@router.post("/{feedback_id}/golden-example", response_model=GoldenExampleResponse, status_code=status.HTTP_201_CREATED)
async def create_golden_example_from_feedback(
    feedback_id: str,
    payload: GoldenExampleCreate,
    current_user: dict = Depends(require_permission("feedback.manage")),
    session: AsyncSession = Depends(get_session),
):
    """Create a golden example from a feedback item."""
    try:
        fb_uuid = uuid.UUID(feedback_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid feedback_id") from e

    result = await session.execute(select(MessageFeedback).where(MessageFeedback.id == fb_uuid))
    feedback = result.scalar_one_or_none()
    if feedback is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feedback not found")

    golden = GoldenExample(
        feedback_id=feedback.id,
        source_type=feedback.feedback_type,
        original_query=feedback.user_message,
        original_response=feedback.bot_message,
        golden_response=payload.golden_response,
        created_by=uuid.UUID(current_user["user_id"]),
        is_active=True,
    )
    session.add(golden)
    feedback.status = "reviewed"
    await session.commit()
    await session.refresh(golden)
    return GoldenExampleResponse.model_validate(golden)


@router.get("/golden-examples", response_model=list[GoldenExampleResponse])
async def list_golden_examples(
    current_user: dict = Depends(require_permission("feedback.manage")),
    session: AsyncSession = Depends(get_session),
    limit: int = 50,
    offset: int = 0,
):
    """List golden examples for admin dashboard."""
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="limit must be between 1 and 200")
    if offset < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="offset must be >= 0")

    result = await session.execute(
        select(GoldenExample)
        .order_by(GoldenExample.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = result.scalars().all()
    return [GoldenExampleResponse.model_validate(r) for r in rows]


@router.patch("/golden-examples/{golden_id}", response_model=GoldenExampleResponse)
async def update_golden_example(
    golden_id: str,
    payload: GoldenExampleUpdate,
    current_user: dict = Depends(require_permission("feedback.manage")),
    session: AsyncSession = Depends(get_session),
):
    """Activate/deactivate a golden example."""
    try:
        ge_uuid = uuid.UUID(golden_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid golden_id") from e

    result = await session.execute(select(GoldenExample).where(GoldenExample.id == ge_uuid))
    golden = result.scalar_one_or_none()
    if golden is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Golden example not found")

    golden.is_active = payload.is_active
    await session.commit()
    await session.refresh(golden)
    return GoldenExampleResponse.model_validate(golden)


@router.delete("/golden-examples/{golden_id}")
async def delete_golden_example(
    golden_id: str,
    current_user: dict = Depends(require_permission("feedback.manage")),
    session: AsyncSession = Depends(get_session),
):
    """Delete a golden example permanently."""
    try:
        ge_uuid = uuid.UUID(golden_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid golden_id") from e

    result = await session.execute(select(GoldenExample).where(GoldenExample.id == ge_uuid))
    golden = result.scalar_one_or_none()
    if golden is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Golden example not found")

    await session.delete(golden)
    await session.commit()
    return {"success": True, "message": "Golden example deleted"}
