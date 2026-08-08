from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.errors import ConflictError, DatabaseError
from app.models import AiStatus, ReviewAction, ReviewStatus, Ticket
from app.schemas import AiReviewRequest
from app.services.ticket_service import add_event, get_ticket_or_raise


def review_ai_suggestion(session: Session, ticket_id: int, payload: AiReviewRequest) -> Ticket:
    """Apply a human review to an existing proposal in one transaction."""

    ticket = get_ticket_or_raise(session, ticket_id)
    if ticket.ai_status is not AiStatus.SUCCEEDED or ticket.review_status is not ReviewStatus.PENDING:
        raise ConflictError("当前工单没有待审核的有效 AI 建议。")

    try:
        event_payload: dict[str, object] = {"action": payload.action.value}
        if payload.action is ReviewAction.CONFIRM:
            if ticket.ai_category is None or ticket.ai_priority is None:
                raise ConflictError("AI 建议数据不完整，不能确认。")
            ticket.final_category = ticket.ai_category
            ticket.final_priority = ticket.ai_priority
            ticket.review_status = ReviewStatus.CONFIRMED
            event_payload.update(
                {"final_category": ticket.final_category.value, "final_priority": ticket.final_priority.value}
            )
        elif payload.action is ReviewAction.MODIFY:
            ticket.final_category = payload.final_category
            ticket.final_priority = payload.final_priority
            ticket.review_status = ReviewStatus.MODIFIED
            event_payload.update(
                {"final_category": ticket.final_category.value, "final_priority": ticket.final_priority.value}
            )
        else:
            ticket.review_status = ReviewStatus.REJECTED

        ticket.reviewer = payload.reviewer.strip()
        ticket.review_reason = payload.reason.strip() if payload.reason else None
        ticket.reviewed_at = datetime.now(timezone.utc)
        ticket.version += 1
        add_event(session, ticket, "AI_REVIEWED", ticket.reviewer, event_payload)
        session.commit()
        session.refresh(ticket)
        return ticket
    except SQLAlchemyError as exc:
        session.rollback()
        raise DatabaseError("保存人工审核结果失败，请稍后重试。") from exc
