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


router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.post("", response_model=TicketRead, status_code=status.HTTP_201_CREATED)
def create_ticket_endpoint(payload: TicketCreate, session: Session = Depends(get_session)) -> TicketRead:
    return create_ticket(session, payload)


@router.get("", response_model=list[TicketRead])
def list_tickets_endpoint(
    final_status: FinalStatus | None = None,
    final_category: Category | None = None,
    final_priority: Priority | None = None,
    submitter: str | None = Query(default=None, min_length=1, max_length=64),
    limit: int = Query(default=50, ge=1, le=100),
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


@router.get("/{ticket_id}", response_model=TicketRead)
def get_ticket_endpoint(ticket_id: int, session: Session = Depends(get_session)) -> TicketRead:
    return get_ticket_or_raise(session, ticket_id)


@router.get("/{ticket_id}/events", response_model=list[TicketEventRead])
def list_ticket_events_endpoint(ticket_id: int, session: Session = Depends(get_session)) -> list[TicketEventRead]:
    return list_ticket_events(session, ticket_id)


@router.patch("/{ticket_id}", response_model=TicketRead)
def update_ticket_endpoint(
    ticket_id: int, payload: TicketUpdate, session: Session = Depends(get_session)
) -> TicketRead:
    return update_ticket(session, ticket_id, payload)


@router.patch("/{ticket_id}/status", response_model=TicketRead)
def transition_ticket_endpoint(
    ticket_id: int, payload: StatusTransitionRequest, session: Session = Depends(get_session)
) -> TicketRead:
    return transition_ticket(session, ticket_id, payload)


@router.delete("/{ticket_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ticket_endpoint(ticket_id: int, session: Session = Depends(get_session)) -> Response:
    delete_ticket(session, ticket_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
