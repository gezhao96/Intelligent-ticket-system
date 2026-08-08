from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app import models  # noqa: F401 - imports ORM models before create_all
from app.api.ai import router as ai_router
from app.api.system import router as system_router
from app.api.tickets import router as tickets_router
from app.db import Base, engine
from app.errors import ApplicationError


logger = logging.getLogger(__name__)


class Utf8JSONResponse(JSONResponse):
    media_type = "application/json; charset=utf-8"


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="智能工单协同系统",
    version="0.1.0",
    description="单机运行的工单管理与 AI 辅助分诊服务。",
    lifespan=lifespan,
    default_response_class=Utf8JSONResponse,
)


@app.exception_handler(ApplicationError)
async def application_error_handler(_, exc: ApplicationError) -> JSONResponse:
    return Utf8JSONResponse(status_code=exc.status_code, content={"code": exc.code, "message": exc.message})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_, exc: RequestValidationError) -> JSONResponse:
    return Utf8JSONResponse(
        status_code=422,
        content={
            "code": "validation_error",
            "message": "请求参数不合法。",
            "details": jsonable_encoder(exc.errors()),
        },
    )


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_error_handler(_, exc: SQLAlchemyError) -> JSONResponse:
    logger.exception("Unhandled SQLAlchemy error", exc_info=exc)
    return Utf8JSONResponse(status_code=500, content={"code": "database_error", "message": "数据库操作失败。"})


@app.exception_handler(Exception)
async def unexpected_error_handler(_, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled application error", exc_info=exc)
    return Utf8JSONResponse(status_code=500, content={"code": "internal_error", "message": "服务器内部错误。"})


@app.get(
    "/health",
    tags=["系统管理"],
    summary="健康检查",
    description="检查服务进程是否可响应。",
    response_description="服务健康状态",
)
def health_check() -> dict[str, str]:
    """返回最小化的服务健康状态。"""

    return {"status": "ok"}


app.include_router(tickets_router)
app.include_router(ai_router)
app.include_router(system_router)
