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


router = APIRouter(prefix="/tickets", tags=["AI 分诊"])


def get_deepseek_client() -> DeepSeekClient:
    return DeepSeekClient(settings)


@router.post(
    "/{ticket_id}/ai-analysis",
    response_model=TicketRead,
    summary="生成 AI 分诊建议",
    description="调用真实 DeepSeek 分析工单，仅保存分类、优先级、摘要和理由等建议，不会修改最终字段。",
    response_description="包含 AI 建议的工单详情",
)
def analyze_ticket_endpoint(
    ticket_id: int,
    session: Session = Depends(get_session),
    client: DeepSeekClient = Depends(get_deepseek_client),
) -> TicketRead:
    ticket, failure = analyze_ticket(session, ticket_id, client)
    if failure is not None:
        raise AiUnavailableError(f"AI 分析不可用：{failure.message}")
    return ticket


@router.post(
    "/{ticket_id}/ai-review",
    response_model=TicketRead,
    summary="人工审核 AI 建议",
    description="选择确认、修改或拒绝 AI 建议；只有确认或修改后，最终分类和优先级才会生效。",
    response_description="审核后的工单详情",
)
def review_ai_suggestion_endpoint(
    ticket_id: int, payload: AiReviewRequest, session: Session = Depends(get_session)
) -> TicketRead:
    return review_ai_suggestion(session, ticket_id, payload)
