from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.core.logging import logger
from backend.app.db.session import get_db
from backend.app.schemas.advisor import AdvisorQueryRequest, AdvisorQueryResponse, AuthUser
from backend.app.services.advisor_orchestrator import AdvisorOrchestrator, advisor_orchestrator
from backend.app.api.deps import get_current_user_optional

router = APIRouter(prefix="/advisor", tags=["Conversational Agricultural Advisor"])


def get_orchestrator() -> AdvisorOrchestrator:
    return advisor_orchestrator


@router.post(
    "/query",
    response_model=AdvisorQueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit query to the conversational agricultural RAG advisor",
    description="Processes farmer queries through a 10-layer grounded RAG pipeline with strict factual verification and safe abstention.",
)
async def query_advisor(
    request: AdvisorQueryRequest,
    db: Session = Depends(get_db),
    orchestrator: AdvisorOrchestrator = Depends(get_orchestrator),
    current_user: Optional[AuthUser] = Depends(get_current_user_optional),
) -> AdvisorQueryResponse:
    try:
        response = await orchestrator.answer_query(db=db, request=request, current_user=current_user)
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Advisor query processing failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error_code": "ADVISOR_PROCESSING_ERROR",
                "message": "The advisory system encountered a temporary error. Please try again shortly.",
            },
        )


@router.get(
    "/conversations/{conversation_id}",
    summary="Get conversation turns under advisor namespace",
)
async def get_advisor_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[AuthUser] = Depends(get_current_user_optional),
):
    from backend.app.api.v1.conversations import get_conversation_history
    return await get_conversation_history(conversation_id=conversation_id, db=db, current_user=current_user)
