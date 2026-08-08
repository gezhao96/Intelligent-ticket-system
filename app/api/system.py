from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_session
from app.services.seed_service import seed_tickets


router = APIRouter(prefix="/system", tags=["系统管理"])


class SeedResult(BaseModel):
    created: int
    existing: int


@router.post(
    "/seed",
    response_model=SeedResult,
    summary="初始化示例工单",
    description="幂等生成 5 条覆盖不同状态和类型的示例工单，重复调用不会重复写入。",
    response_description="本次创建与已存在的示例工单数量",
)
def seed_endpoint(session: Session = Depends(get_session)) -> SeedResult:
    created, existing = seed_tickets(session)
    return SeedResult(created=created, existing=existing)
