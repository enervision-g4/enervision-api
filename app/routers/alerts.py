from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Alert
from app.schemas import AlertOut
from app.security import get_current_subject

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertOut])
def list_alerts(
    site_id: str | None = None,
    severity: str | None = None,
    db: Session = Depends(get_db),
    _subject: str = Depends(get_current_subject),
):
    stmt = select(Alert)
    if site_id:
        stmt = stmt.where(Alert.site_id == site_id)
    if severity:
        stmt = stmt.where(Alert.severity == severity)
    stmt = stmt.order_by(Alert.timestamp.desc())

    return db.scalars(stmt).all()
