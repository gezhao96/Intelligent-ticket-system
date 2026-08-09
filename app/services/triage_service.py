from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.clients.deepseek import AiProviderFailure, DeepSeekClient
from app.core.config import settings
from app.errors import ConflictError, DatabaseError
from app.models import AiStatus, ReviewStatus, Ticket
from app.services.ticket_service import add_event, get_ticket_or_raise


def analyze_ticket(
    session: Session, ticket_id: int, client: DeepSeekClient | None = None
) -> tuple[Ticket, AiProviderFailure | None]:
    """保存经校验的 AI 建议；整个流程绝不触碰 final_* 字段。"""

    ticket = get_ticket_or_raise(session, ticket_id)
    if ticket.ai_status is AiStatus.SUCCEEDED or ticket.review_status is ReviewStatus.PENDING:
        # 待审核建议不可被覆盖，保证人工看到的内容与审核对象一致。
        raise ConflictError("该工单已有待审核的 AI 建议，请先完成审核。")
    if ticket.review_status in {ReviewStatus.CONFIRMED, ReviewStatus.MODIFIED, ReviewStatus.REJECTED}:
        raise ConflictError("该工单的 AI 建议已审核，不允许重复分析。")

    client = client or DeepSeekClient(settings)
    try:
        suggestion, raw_response = client.analyze(title=ticket.title, description=ticket.description)
    except AiProviderFailure as failure:
        # 外部服务失败时持久化失败状态，再让路由返回 503。
        _persist_ai_failure(session, ticket, client, failure)
        return ticket, failure

    try:
        # 只更新 ai_* 字段，final_* 始终保留人工当前决定。
        ticket.ai_category = suggestion.category
        ticket.ai_priority = suggestion.priority
        ticket.ai_summary = suggestion.summary
        ticket.ai_reason = suggestion.reason
        ticket.ai_injection_detected = suggestion.injection_detected
        ticket.ai_status = AiStatus.SUCCEEDED
        ticket.ai_model = client.model
        ticket.ai_prompt_version = client.prompt_version
        ticket.ai_raw_response = raw_response
        ticket.ai_error_code = None
        ticket.review_status = ReviewStatus.PENDING
        ticket.version += 1
        add_event(
            session,
            ticket,
            "AI_SUGGESTED",
            "deepseek",
            {
                "category": suggestion.category.value,
                "priority": suggestion.priority.value,
                "injection_detected": suggestion.injection_detected,
                "prompt_version": client.prompt_version,
            },
        )
        session.commit()
        session.refresh(ticket)
        return ticket, None
    except SQLAlchemyError as exc:
        session.rollback()
        raise DatabaseError("保存 AI 建议失败，请稍后重试。") from exc


def _persist_ai_failure(
    session: Session, ticket: Ticket, client: DeepSeekClient, failure: AiProviderFailure
) -> None:
    """仅保存安全失败信息，并保持所有最终字段不变。"""

    try:
        ticket.ai_category = None
        ticket.ai_priority = None
        ticket.ai_summary = None
        ticket.ai_reason = None
        ticket.ai_injection_detected = None
        ticket.ai_status = AiStatus.FAILED
        ticket.ai_model = client.model
        ticket.ai_prompt_version = client.prompt_version
        ticket.ai_raw_response = None
        ticket.ai_error_code = failure.code
        ticket.review_status = ReviewStatus.NOT_REVIEWED
        ticket.version += 1
        add_event(
            session,
            ticket,
            "AI_FAILED",
            "deepseek",
            {"code": failure.code, "prompt_version": client.prompt_version},
        )
        session.commit()
        session.refresh(ticket)
    except SQLAlchemyError as exc:
        session.rollback()
        raise DatabaseError("保存 AI 失败状态失败，请稍后重试。") from exc
