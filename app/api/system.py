from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_session
from app.services.seed_service import seed_tickets


router = APIRouter(prefix="/system", tags=["system"])


class SeedResult(BaseModel):
    created: int
    existing: int


@router.post("/seed", response_model=SeedResult)
def seed_endpoint(session: Session = Depends(get_session)) -> SeedResult:
    created, existing = seed_tickets(session)
    return SeedResult(created=created, existing=existing)
