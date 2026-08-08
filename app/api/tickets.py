from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Category, FinalStatus, Priority
from app.schemas import StatusTransitionRequest, TicketCreate, TicketEventRead, TicketRead, TicketUpdate
from app.services.ticket_service import (
    create_ticket,
    delete_ticket,
    get_ticket_or_raise,
    list_ticket_events,
    list_tickets,
    transition_ticket,
    update_ticket,
)


router = APIRouter(prefix="/tickets", tags=["工单管理"])


@router.post(
    "",
    response_model=TicketRead,
    status_code=status.HTTP_201_CREATED,
    summary="创建工单",
    description="提交标题、描述和提交人，创建一张待处理工单。最终分类和优先级需在 AI 审核后产生。",
    response_description="工单创建成功",
)
def create_ticket_endpoint(payload: TicketCreate, session: Session = Depends(get_session)) -> TicketRead:
    return create_ticket(session, payload)


@router.get(
    "",
    response_model=list[TicketRead],
    summary="查询工单列表",
    description="可按最终状态、最终分类、最终优先级和提交人组合筛选。",
    response_description="符合筛选条件的工单列表",
)
def list_tickets_endpoint(
    final_status: FinalStatus | None = Query(default=None, description="按最终处理状态筛选"),
    final_category: Category | None = Query(default=None, description="按最终分类筛选"),
    final_priority: Priority | None = Query(default=None, description="按最终优先级筛选"),
    submitter: str | None = Query(default=None, min_length=1, max_length=64, description="按提交人精确筛选"),
    limit: int = Query(default=50, ge=1, le=100, description="最多返回的工单数量"),
    session: Session = Depends(get_session),
) -> list[TicketRead]:
    return list_tickets(
        session,
        final_status=final_status,
        final_category=final_category,
        final_priority=final_priority,
        submitter=submitter,
        limit=limit,
    )


@router.get(
    "/{ticket_id}",
    response_model=TicketRead,
    summary="查看工单详情",
    description="查看工单基础信息、AI 分诊建议、最终结果和审核状态。",
    response_description="工单详情",
)
def get_ticket_endpoint(ticket_id: int, session: Session = Depends(get_session)) -> TicketRead:
    return get_ticket_or_raise(session, ticket_id)


@router.get(
    "/{ticket_id}/events",
    response_model=list[TicketEventRead],
    summary="查看工单审计记录",
    description="按时间顺序返回创建、更新、状态流转、AI 分析和人工审核事件。",
    response_description="工单审计事件列表",
)
def list_ticket_events_endpoint(ticket_id: int, session: Session = Depends(get_session)) -> list[TicketEventRead]:
    return list_ticket_events(session, ticket_id)


@router.patch(
    "/{ticket_id}",
    response_model=TicketRead,
    summary="修改工单基础信息",
    description="仅可修改标题、描述或提交人；最终分类、优先级和状态由各自的独立流程更新。",
    response_description="更新后的工单详情",
)
def update_ticket_endpoint(
    ticket_id: int, payload: TicketUpdate, session: Session = Depends(get_session)
) -> TicketRead:
    return update_ticket(session, ticket_id, payload)


@router.patch(
    "/{ticket_id}/status",
    response_model=TicketRead,
    summary="更新工单处理状态",
    description="依据状态机将工单流转为处理中、已解决、已关闭或已取消。",
    response_description="状态更新后的工单详情",
)
def transition_ticket_endpoint(
    ticket_id: int, payload: StatusTransitionRequest, session: Session = Depends(get_session)
) -> TicketRead:
    return transition_ticket(session, ticket_id, payload)


@router.delete(
    "/{ticket_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除待处理工单",
    description="仅待处理状态的工单允许软删除，历史审计信息仍会保留。",
    response_description="工单已删除",
)
def delete_ticket_endpoint(ticket_id: int, session: Session = Depends(get_session)) -> Response:
    delete_ticket(session, ticket_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
