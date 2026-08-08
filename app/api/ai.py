from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.clients.deepseek import DeepSeekClient
from app.core.config import settings
from app.db import get_session
from app.errors import AiUnavailableError
from app.schemas import AiReviewRequest, TicketRead
from app.services.review_service import review_ai_suggestion
from app.services.triage_service import analyze_ticket


router = APIRouter(prefix="/tickets", tags=["ai"])


def get_deepseek_client() -> DeepSeekClient:
    return DeepSeekClient(settings)


@router.post("/{ticket_id}/ai-analysis", response_model=TicketRead)
def analyze_ticket_endpoint(
    ticket_id: int,
    session: Session = Depends(get_session),
    client: DeepSeekClient = Depends(get_deepseek_client),
) -> TicketRead:
    ticket, failure = analyze_ticket(session, ticket_id, client)
    if failure is not None:
        raise AiUnavailableError(f"AI 分析不可用：{failure.message}")
    return ticket


@router.post("/{ticket_id}/ai-review", response_model=TicketRead)
def review_ai_suggestion_endpoint(
    ticket_id: int, payload: AiReviewRequest, session: Session = Depends(get_session)
) -> TicketRead:
    return review_ai_suggestion(session, ticket_id, payload)
