from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.api.deps import get_current_user
from app.db.base import SessionLocal
from app.db.models import AuditLog
from app.schemas.common import ok

router = APIRouter(prefix="/api/v1/logs", tags=["logs"], dependencies=[Depends(get_current_user)])


@router.get("")
async def list_logs(
    category: str | None = None,
    level: str | None = None,
    date: str | None = None,
    strategy: str | None = None,
    limit: int = 200,
):
    query = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    if category:
        query = query.where(AuditLog.category == category)
    if level:
        query = query.where(AuditLog.level == level.upper())
    if strategy:
        query = query.where(AuditLog.strategy == strategy)
    if date:
        day = datetime.fromisoformat(date).date()
        query = query.where(AuditLog.created_at >= day).where(AuditLog.created_at < day.__class__.fromordinal(day.toordinal() + 1))

    async with SessionLocal() as session:
        rows = (await session.execute(query)).scalars().all()

    return ok(
        [
            {
                "id": r.id,
                "time": r.created_at.isoformat() if r.created_at else None,
                "category": r.category,
                "level": r.level,
                "message": r.message,
                "strategy": r.strategy,
                "context": r.context,
            }
            for r in rows
        ]
    )
