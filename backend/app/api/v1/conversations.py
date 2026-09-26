import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.models.models import Conversation, QueryLog, ResponseLog
from backend.app.schemas.advisor import ConversationHistoryResponse, ConversationTurnDTO

router = APIRouter(prefix="/conversations", tags=["Conversations"])


@router.get(
    "/{conversation_id}",
    response_model=ConversationHistoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get chronologically ordered turns for a conversation",
)
async def get_conversation_history(
    conversation_id: str,
    db: Session = Depends(get_db),
) -> ConversationHistoryResponse:
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
