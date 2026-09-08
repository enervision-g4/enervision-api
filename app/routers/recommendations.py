from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Recommendation
from app.schemas import RecommendationOut, RecommendationPage
from app.security import get_current_subject

router = APIRouter(prefix="/api/v1/recommendations", tags=["recommendations"])

# Colonnes autorisées pour sort_by — même principe de whitelist explicite que
# /api/v1/alerts, pour ne jamais exposer un tri sur une colonne arbitraire à
# partir d'une chaîne fournie par le client.
SORTABLE_COLUMNS = {
    "timestamp": Recommendation.timestamp,
    "site_id": Recommendation.site_id,
    "status": Recommendation.status,
}


def _apply_filters(stmt, site_id, status):
    if site_id:
        stmt = stmt.where(Recommendation.site_id == site_id)
    if status:
        stmt = stmt.where(Recommendation.status == status)
    return stmt


@router.get("", response_model=RecommendationPage)
def list_recommendations(
    site_id: str | None = None,
    status: str | None = None,
    sort_by: Literal["timestamp", "site_id", "status"] = "timestamp",
    order: Literal["asc", "desc"] = "desc",
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=25, ge=1, le=200),
    db: Session = Depends(get_db),
    _subject: str = Depends(get_current_subject),
):
    """Recommandations d'actions correctives, générées à partir des
    prédictions qui dépassent leur seuil.

    Paginée/triable comme /api/v1/alerts (même enveloppe {items, total,
    page, limit}), pour que le dashboard réutilise le même composant de
    pagination des deux côtés plutôt que de gérer un format différent ici.
    """
    total = db.scalar(
        _apply_filters(select(func.count()).select_from(Recommendation), site_id, status)
    )

    column = SORTABLE_COLUMNS[sort_by]
    ordered_column = column.asc() if order == "asc" else column.desc()
    stmt = _apply_filters(select(Recommendation), site_id, status)
    stmt = stmt.order_by(ordered_column).offset((page - 1) * limit).limit(limit)

    items = db.scalars(stmt).all()
    return RecommendationPage(
        items=[RecommendationOut.model_validate(item) for item in items],
        total=total or 0,
        page=page,
        limit=limit,
    )
