from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Recommendation
from app.schemas import RecommendationOut
from app.security import get_current_subject

router = APIRouter(prefix="/api/v1/recommendations", tags=["recommendations"])


@router.get("", response_model=list[RecommendationOut])
def list_recommendations(
    site_id: str | None = None,
    status: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    _subject: str = Depends(get_current_subject),
):
    """Recommandations d'actions correctives, générées à partir des
    prédictions. Les plus récentes d'abord, même logique de tri que
    /api/v1/alerts."""
    stmt = select(Recommendation)
    if site_id:
        stmt = stmt.where(Recommendation.site_id == site_id)
    if status:
        stmt = stmt.where(Recommendation.status == status)
    stmt = stmt.order_by(Recommendation.timestamp.desc()).limit(limit)

    return db.scalars(stmt).all()
