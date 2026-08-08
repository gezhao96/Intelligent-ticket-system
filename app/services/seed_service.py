from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.errors import DatabaseError
from app.models import Category, FinalStatus, Priority, Ticket
from app.services.ticket_service import add_event, build_content_hash


SEED_TICKETS = (
    ("无法登录公司邮箱", "新员工无法使用公司账号登录邮箱。", "张伟", Category.ACCOUNT_ACCESS, Priority.P2, FinalStatus.OPEN),
    ("财务软件启动闪退", "打开财务客户端后立即退出。", "李娜", Category.SOFTWARE_INCIDENT, Priority.P1, FinalStatus.IN_PROGRESS),
    ("研发网络间歇中断", "研发办公区网络频繁断开，影响代码同步。", "王强", Category.NETWORK, Priority.P1, FinalStatus.RESOLVED),
    ("三楼打印机缺墨", "三楼打印机提示墨盒余量不足。", "赵敏", Category.HARDWARE_OFFICE, Priority.P3, FinalStatus.CLOSED),
    ("申请新增知识库标签", "希望为知识库文章增加项目标签。", "陈晨", Category.OTHER, Priority.P3, FinalStatus.CANCELLED),
)


def seed_tickets(session: Session) -> tuple[int, int]:
    """Create a reproducible demonstration dataset without duplicating seed rows."""

    created = 0
    existing = 0
    try:
        for title, description, submitter, category, priority, final_status in SEED_TICKETS:
            content_hash = build_content_hash(title, description)
            ticket = session.scalar(select(Ticket).where(Ticket.content_hash == content_hash))
            if ticket is not None:
                existing += 1
                continue
            ticket = Ticket(
                title=title,
                description=description,
                submitter=submitter,
                content_hash=content_hash,
                final_category=category,
                final_priority=priority,
                final_status=final_status,
            )
            session.add(ticket)
            session.flush()
            add_event(session, ticket, "SEED_CREATED", "system", {"ticket_id": ticket.id})
            created += 1
        session.commit()
        return created, existing
    except SQLAlchemyError as exc:
        session.rollback()
        raise DatabaseError("初始化示例数据失败，请稍后重试。") from exc
