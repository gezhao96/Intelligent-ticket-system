from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from app.models import AiStatus, Category, FinalStatus, Priority, ReviewAction, ReviewStatus

Title = Annotated[str, Field(min_length=1, max_length=120)]
Description = Annotated[str, Field(min_length=1, max_length=4000)]
PersonName = Annotated[str, Field(min_length=1, max_length=64)]


class TicketCreate(BaseModel):
    """创建工单只接收原始问题信息，分诊结果必须经 AI 审核流程写入。"""
    model_config = ConfigDict(extra="forbid")

    title: Title
    description: Description
    submitter: PersonName
    allow_duplicate: bool = False


class TicketUpdate(BaseModel):
    """仅允许更正基础信息；最终分诊结果与状态均使用独立流程更新。"""
    model_config = ConfigDict(extra="forbid")

    title: Title | None = None
    description: Description | None = None
    submitter: PersonName | None = None


class StatusTransitionRequest(BaseModel):
    """人工发起的状态流转请求。"""
    final_status: FinalStatus
    actor: PersonName = "api_user"


class TicketRead(BaseModel):
    """对外返回工单当前快照，不暴露原始模型文本。"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    submitter: str
    content_hash: str
    version: int
    final_category: Category | None
    final_priority: Priority | None
    final_status: FinalStatus
    ai_category: Category | None
    ai_priority: Priority | None
    ai_summary: str | None
    ai_reason: str | None
    ai_status: AiStatus
    ai_status_label: str
    ai_injection_detected: bool | None
    ai_model: str | None
    ai_prompt_version: str | None
    ai_error_code: str | None
    review_status: ReviewStatus
    reviewer: str | None
    review_reason: str | None
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TicketEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_id: int
    event_type: str
    actor: str
    payload_json: str | None
    created_at: datetime


class AiSuggestionOutput(BaseModel):
    """模型输出落库前必须通过的严格结构。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    category: Category
    priority: Priority
    summary: Annotated[str, Field(min_length=1, max_length=80)]
    reason: Annotated[str, Field(min_length=1, max_length=240)]
    injection_detected: StrictBool


class AiReviewRequest(BaseModel):
    action: ReviewAction
    reviewer: PersonName
    reason: Annotated[str | None, Field(max_length=240)] = None
    final_category: Category | None = None
    final_priority: Priority | None = None

    @model_validator(mode="after")
    def validate_action_fields(self) -> "AiReviewRequest":
        # 不同审核动作要求不同的人工输入，提前阻止含糊请求。
        if self.action is ReviewAction.MODIFY:
            if self.final_category is None or self.final_priority is None:
                raise ValueError("修改 AI 建议时必须同时提供最终分类和优先级。")
        elif self.action is ReviewAction.REJECT:
            if not self.reason or not self.reason.strip():
                raise ValueError("拒绝 AI 建议时必须说明原因。")
            if self.final_category is not None or self.final_priority is not None:
                raise ValueError("拒绝 AI 建议时不能提交最终分类或优先级。")
        elif self.final_category is not None or self.final_priority is not None:
            raise ValueError("确认 AI 建议时不应提交最终分类或优先级。")
        return self


class ErrorResponse(BaseModel):
    code: str
    message: str
