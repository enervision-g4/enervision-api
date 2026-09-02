from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import MeasureRaw
from app.schemas import ReadingOut
from app.security import get_current_subject

router = APIRouter(prefix="/api/v1/readings", tags=["readings"])


@router.get("", response_model=list[ReadingOut])
def list_readings(
    site_id: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    _subject: str = Depends(get_current_subject),
):
    end_time = end_time or datetime.now(timezone.utc)
    start_time = start_time or end_time - timedelta(hours=24)

    stmt = select(MeasureRaw).where(
        MeasureRaw.timestamp >= start_time,
        MeasureRaw.timestamp <= end_time,
    )
    if site_id:
        stmt = stmt.where(MeasureRaw.site_id == site_id)
    stmt = stmt.order_by(MeasureRaw.timestamp.asc()).limit(limit)

    return db.scalars(stmt).all()
