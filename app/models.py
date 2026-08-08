from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utc_now() -> datetime:
    # 所有业务时间统一使用 UTC，避免本机时区影响审计顺序。
    return datetime.now(timezone.utc)


class Category(StrEnum):
    # 枚举成员名保持稳定，API 与 Swagger 展示值使用中文。
    ACCOUNT_ACCESS = "账号权限"
    SOFTWARE_INCIDENT = "软件故障"
    NETWORK = "网络问题"
    HARDWARE_OFFICE = "办公硬件"
    OTHER = "其他"


class Priority(StrEnum):
    # 优先级从紧急的 P0 到低影响的 P3。
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class FinalStatus(StrEnum):
    # 最终业务状态由人工操作；API 与 Swagger 展示值使用中文。
    OPEN = "待处理"
    IN_PROGRESS = "处理中"
    RESOLVED = "已解决"
    CLOSED = "已关闭"
    CANCELLED = "已取消"


class AiStatus(StrEnum):
    # 模型调用生命周期，与人工审核状态分开记录。
    NOT_REQUESTED = "NOT_REQUESTED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class ReviewStatus(StrEnum):
    # AI 建议的人工审核状态。
    NOT_REVIEWED = "NOT_REVIEWED"
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    MODIFIED = "MODIFIED"
    REJECTED = "REJECTED"


class ReviewAction(StrEnum):
    # 审核接口接收的三种动作。
    CONFIRM = "CONFIRM"
    MODIFY = "MODIFY"
    REJECT = "REJECT"


class Ticket(Base):
    """工单当前快照：保存基础信息、AI 建议和人工最终结果。"""
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    submitter: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # AI 仅能写入建议字段；这些值不会自动成为有效工单结果。
    ai_category: Mapped[Category | None] = mapped_column(
        Enum(Category, native_enum=False, validate_strings=True), nullable=True
    )
    ai_priority: Mapped[Priority | None] = mapped_column(
        Enum(Priority, native_enum=False, validate_strings=True), nullable=True
    )
    ai_summary: Mapped[str | None] = mapped_column(String(80), nullable=True)
    ai_reason: Mapped[str | None] = mapped_column(String(240), nullable=True)
    ai_status: Mapped[AiStatus] = mapped_column(
        Enum(AiStatus, native_enum=False, validate_strings=True),
        nullable=False,
        default=AiStatus.NOT_REQUESTED,
    )
    ai_injection_detected: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    ai_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ai_prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ai_raw_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # 最终分类与优先级只能由人工确认或修改 AI 建议写入；状态由人工流转。
    final_category: Mapped[Category | None] = mapped_column(
        Enum(Category, native_enum=False, validate_strings=True), nullable=True
    )
    final_priority: Mapped[Priority | None] = mapped_column(
        Enum(Priority, native_enum=False, validate_strings=True), nullable=True
    )
    final_status: Mapped[FinalStatus] = mapped_column(
        Enum(FinalStatus, native_enum=False, validate_strings=True),
        nullable=False,
        default=FinalStatus.OPEN,
    )
    review_status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus, native_enum=False, validate_strings=True),
        nullable=False,
        default=ReviewStatus.NOT_REVIEWED,
    )
    reviewer: Mapped[str | None] = mapped_column(String(64), nullable=True)
    review_reason: Mapped[str | None] = mapped_column(String(240), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    events: Mapped[list[TicketEvent]] = relationship(back_populates="ticket", cascade="all, delete-orphan")


class TicketEvent(Base):
    """不可变的审计事件，用于还原一次工单的处理过程。"""
    __tablename__ = "ticket_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    ticket: Mapped[Ticket] = relationship(back_populates="events")
