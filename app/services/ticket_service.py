from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.errors import ConflictError, DatabaseError, NotFoundError
from app.models import Category, FinalStatus, Priority, Ticket, TicketEvent
from app.schemas import StatusTransitionRequest, TicketCreate, TicketUpdate


ALLOWED_STATUS_TRANSITIONS: dict[FinalStatus, set[FinalStatus]] = {
    # 显式白名单避免任意跳转破坏业务处理过程。
    FinalStatus.OPEN: {FinalStatus.IN_PROGRESS, FinalStatus.CANCELLED},
    FinalStatus.IN_PROGRESS: {FinalStatus.RESOLVED, FinalStatus.CANCELLED},
    FinalStatus.RESOLVED: {FinalStatus.CLOSED, FinalStatus.IN_PROGRESS},
    FinalStatus.CLOSED: set(),
    FinalStatus.CANCELLED: set(),
}


def normalize_content(value: str) -> str:
    # 去除格式差异后再比较，避免仅靠空格或大小写绕过重复检测。
    return re.sub(r"\s+", " ", value.strip()).casefold()


def build_content_hash(title: str, description: str) -> str:
    # 标题与描述是“内容完全相同”的唯一判据，不把提交人纳入哈希。
    content = f"{normalize_content(title)}\n{normalize_content(description)}"
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def add_event(session: Session, ticket: Ticket, event_type: str, actor: str, payload: dict[str, object]) -> None:
    # 所有重要变更都追加事件，而非覆盖历史记录。
    session.add(
        TicketEvent(
            ticket=ticket,
            event_type=event_type,
            actor=actor,
            payload_json=json.dumps(payload, ensure_ascii=False, sort_keys=True),
        )
    )


def get_ticket_or_raise(session: Session, ticket_id: int) -> Ticket:
    # 软删除工单对普通读取接口表现为不存在。
    ticket = session.scalar(select(Ticket).where(Ticket.id == ticket_id, Ticket.is_deleted.is_(False)))
    if ticket is None:
        raise NotFoundError(f"工单 {ticket_id} 不存在。")
    return ticket


def list_tickets(
    session: Session,
    *,
    final_status: FinalStatus | None = None,
    final_category: Category | None = None,
    final_priority: Priority | None = None,
    submitter: str | None = None,
    limit: int = 50,
) -> list[Ticket]:
    """按最终有效字段组合筛选；AI 建议字段不参与业务查询。"""
    statement = select(Ticket).where(Ticket.is_deleted.is_(False))
    if final_status is not None:
        statement = statement.where(Ticket.final_status == final_status)
    if final_category is not None:
        statement = statement.where(Ticket.final_category == final_category)
    if final_priority is not None:
        statement = statement.where(Ticket.final_priority == final_priority)
    if submitter is not None:
        statement = statement.where(Ticket.submitter == submitter.strip())
    statement = statement.order_by(Ticket.created_at.desc()).limit(limit)

    try:
        return list(session.scalars(statement))
    except SQLAlchemyError as exc:
        raise DatabaseError("查询工单失败，请稍后重试。") from exc


def create_ticket(session: Session, payload: TicketCreate) -> Ticket:
    """创建工单，并在同一事务中写入创建事件。"""
    content_hash = build_content_hash(payload.title, payload.description)
    duplicate = _find_recent_duplicate(session, content_hash)
    if duplicate is not None and not payload.allow_duplicate:
        raise ConflictError(f"检测到 24 小时内内容完全相同的工单，已有工单 ID：{duplicate.id}。")

    ticket = Ticket(
        title=payload.title.strip(),
        description=payload.description.strip(),
        submitter=payload.submitter.strip(),
        content_hash=content_hash,
    )
    try:
        session.add(ticket)
        session.flush()
        add_event(session, ticket, "TICKET_CREATED", ticket.submitter, {"ticket_id": ticket.id})
        if duplicate is not None:
            add_event(session, ticket, "DUPLICATE_ALLOWED", ticket.submitter, {"duplicate_ticket_id": duplicate.id})
        session.commit()
        session.refresh(ticket)
        return ticket
    except SQLAlchemyError as exc:
        session.rollback()
        raise DatabaseError("创建工单失败，请稍后重试。") from exc


def update_ticket(session: Session, ticket_id: int, payload: TicketUpdate) -> Ticket:
    ticket = get_ticket_or_raise(session, ticket_id)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return ticket

    try:
        for field, value in changes.items():
            if isinstance(value, str):
                value = value.strip()
            setattr(ticket, field, value)
        if "title" in changes or "description" in changes:
            ticket.content_hash = build_content_hash(ticket.title, ticket.description)
            duplicate = _find_recent_duplicate(session, ticket.content_hash, exclude_ticket_id=ticket.id)
            if duplicate is not None:
                raise ConflictError(f"更新后会与工单 {duplicate.id} 形成完全重复内容。")
        ticket.version += 1
        add_event(session, ticket, "TICKET_UPDATED", "api_user", {"fields": sorted(changes)})
        session.commit()
        session.refresh(ticket)
        return ticket
    except SQLAlchemyError as exc:
        session.rollback()
        raise DatabaseError("更新工单失败，请稍后重试。") from exc


def _find_recent_duplicate(session: Session, content_hash: str, exclude_ticket_id: int | None = None) -> Ticket | None:
    # 默认只拦截 24 小时内的重复，避免长期历史工单阻止真实的新问题。
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    statement = select(Ticket).where(
        Ticket.content_hash == content_hash,
        Ticket.is_deleted.is_(False),
        Ticket.created_at >= cutoff,
    )
    if exclude_ticket_id is not None:
        statement = statement.where(Ticket.id != exclude_ticket_id)
    return session.scalar(statement.order_by(Ticket.created_at.desc()))


def delete_ticket(session: Session, ticket_id: int) -> None:
    """仅对未处理工单执行软删除，保留审计记录。"""
    ticket = get_ticket_or_raise(session, ticket_id)
    if ticket.final_status is not FinalStatus.OPEN:
        raise ConflictError("仅待处理状态的工单允许删除，其他工单请使用取消状态。")

    try:
        ticket.is_deleted = True
        ticket.deleted_at = datetime.now(timezone.utc)
        ticket.version += 1
        add_event(session, ticket, "TICKET_DELETED", "api_user", {"ticket_id": ticket.id})
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        raise DatabaseError("删除工单失败，请稍后重试。") from exc


def transition_ticket(session: Session, ticket_id: int, payload: StatusTransitionRequest) -> Ticket:
    """依据状态白名单完成人工流转，并记录变更前后状态。"""
    ticket = get_ticket_or_raise(session, ticket_id)
    old_status = ticket.final_status
    target_status = payload.final_status

    if target_status is old_status:
        raise ConflictError(f"工单当前已经是 {old_status.value} 状态。")
    if target_status not in ALLOWED_STATUS_TRANSITIONS[old_status]:
        allowed = ", ".join(status.value for status in ALLOWED_STATUS_TRANSITIONS[old_status]) or "无"
        raise ConflictError(f"不允许从 {old_status.value} 流转到 {target_status.value}，允许目标：{allowed}。")

    try:
        ticket.final_status = target_status
        ticket.version += 1
        add_event(
            session,
            ticket,
            "STATUS_CHANGED",
            payload.actor.strip(),
            {"from": old_status.value, "to": target_status.value},
        )
        session.commit()
        session.refresh(ticket)
        return ticket
    except SQLAlchemyError as exc:
        session.rollback()
        raise DatabaseError("更新工单状态失败，请稍后重试。") from exc


def list_ticket_events(session: Session, ticket_id: int) -> list[TicketEvent]:
    """按时间正序返回工单历史，便于演示可追溯性。"""
    get_ticket_or_raise(session, ticket_id)
    try:
        statement = select(TicketEvent).where(TicketEvent.ticket_id == ticket_id).order_by(TicketEvent.created_at.asc())
        return list(session.scalars(statement))
    except SQLAlchemyError as exc:
        raise DatabaseError("查询工单事件失败，请稍后重试。") from exc
