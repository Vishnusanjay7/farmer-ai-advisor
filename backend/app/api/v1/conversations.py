import uuid
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.models.models import Conversation, QueryLog, ResponseLog, FarmerProfile
from backend.app.schemas.advisor import (
    ConversationHistoryResponse,
    ConversationTurnDTO,
    ConversationListResponse,
    ConversationSummaryDTO,
    AuthUser,
)
from backend.app.api.deps import get_current_user, get_current_user_optional

router = APIRouter(prefix="/conversations", tags=["Conversations"])


@router.get(
    "",
    response_model=ConversationListResponse,
    status_code=status.HTTP_200_OK,
    summary="List persistent conversations for the authenticated user",
)
async def list_user_conversations(
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
) -> ConversationListResponse:
    """Returns chronologically ordered conversation summaries for the authenticated farmer."""
    session_key = f"user-{current_user.id}"
    farmer = db.query(FarmerProfile).filter(FarmerProfile.session_id == session_key).first()
    if not farmer:
        return ConversationListResponse(total=0, conversations=[])

    convs = (
        db.query(Conversation)
        .filter(Conversation.farmer_id == farmer.id)
        .order_by(Conversation.updated_at.desc())
        .all()
    )

    summaries: List[ConversationSummaryDTO] = []
    for c in convs:
        queries = (
            db.query(QueryLog)
            .filter(QueryLog.conversation_id == c.id)
            .order_by(QueryLog.created_at.asc())
            .all()
        )
        last_q = queries[-1] if queries else None
        summaries.append(
            ConversationSummaryDTO(
                id=c.id,
                title=c.title or (f"Advisory Query: {last_q.raw_transcript[:40]}" if last_q else "New Conversation"),
                created_at=c.created_at.isoformat() if c.created_at else "",
                updated_at=c.updated_at.isoformat() if c.updated_at else "",
                total_turns=len(queries),
                last_query=last_q.raw_transcript if last_q else None,
                detected_language=last_q.detected_language if last_q else None,
            )
        )

    return ConversationListResponse(total=len(summaries), conversations=summaries)


@router.get(
    "/{conversation_id}",
    response_model=ConversationHistoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get chronologically ordered turns for a conversation with authorization checks",
)
async def get_conversation_history(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[AuthUser] = Depends(get_current_user_optional),
) -> ConversationHistoryResponse:
    """
    Retrieves full conversation history.
    Enforces authorization: if owned by a specific user, access by another user or guest returns 403 Forbidden.
    """
    try:
        conv_uuid = str(uuid.UUID(str(conversation_id).strip()))
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "INVALID_CONVERSATION_ID",
                "message": f"Invalid conversation ID format: '{conversation_id}'. Must be a valid UUID.",
            },
        )

    conv = db.query(Conversation).filter(Conversation.id == conv_uuid).first()
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "CONVERSATION_NOT_FOUND", "message": f"Conversation '{conversation_id}' not found."},
        )

    # Server-enforced authorization check
    if conv.farmer and conv.farmer.session_id.startswith("user-"):
        owner_user_id = conv.farmer.session_id.removeprefix("user-")
        if not current_user or str(current_user.id) != owner_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error_code": "FORBIDDEN",
                    "message": "You do not have access to this conversation.",
                },
            )

    queries = (
        db.query(QueryLog)
        .filter(QueryLog.conversation_id == conv_uuid)
        .order_by(QueryLog.created_at.asc())
        .all()
    )

    turns = []
    for q in queries:
        resp = db.query(ResponseLog).filter(ResponseLog.query_id == q.id).first()
        turns.append(
            ConversationTurnDTO(
                query_id=q.id,
                conversation_id=q.conversation_id,
                input_channel=q.input_channel or "text",
                detected_language=q.detected_language or "hi-IN",
                query_text=q.raw_transcript,
                classified_intent=q.classified_intent or "UNKNOWN",
                extracted_entities=q.extracted_entities or {},
                response_text=resp.response_text if resp else "",
                is_grounded=resp.is_grounded if resp else False,
                disclaimer_applied=resp.disclaimer_applied if resp else False,
                citations=resp.retrieved_sources if resp and resp.retrieved_sources else [],
                created_at=q.created_at.isoformat() if q.created_at else "",
            )
        )

    return ConversationHistoryResponse(
        conversation_id=conv.id,
        title=conv.title,
        total_turns=len(turns),
        turns=turns,
    )


@router.delete(
    "/{conversation_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a conversation and its turn history",
)
async def delete_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    """Deletes conversation if owned by the current authenticated user."""
    try:
        conv_uuid = str(uuid.UUID(str(conversation_id).strip()))
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "INVALID_CONVERSATION_ID",
                "message": f"Invalid conversation ID format: '{conversation_id}'. Must be a valid UUID.",
            },
        )

    conv = db.query(Conversation).filter(Conversation.id == conv_uuid).first()
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "CONVERSATION_NOT_FOUND", "message": f"Conversation '{conversation_id}' not found."},
        )

    # Check ownership
    session_key = f"user-{current_user.id}"
    if not conv.farmer or conv.farmer.session_id != session_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error_code": "FORBIDDEN",
                "message": "You do not have permission to delete this conversation.",
            },
        )

    db.delete(conv)
    db.commit()
    return {"message": "Conversation deleted successfully", "conversation_id": conv_uuid}
