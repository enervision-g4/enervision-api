from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Prediction
from app.schemas import PredictionOut
from app.security import get_current_subject

router = APIRouter(prefix="/api/v1/predictions", tags=["predictions"])


@router.get("", response_model=list[PredictionOut])
def list_predictions(
    site_id: str | None = None,
    model_version: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    _subject: str = Depends(get_current_subject),
):
    """Prédictions de consommation issues du modèle ML.

    Triées par target_timestamp (l'horizon prédit) croissant : c'est
    l'ordre attendu pour tracer une courbe de prévision sur le dashboard,
    à ne pas confondre avec `timestamp` qui est la date de génération de
    la prédiction.
    """
    stmt = select(Prediction)
    if site_id:
        stmt = stmt.where(Prediction.site_id == site_id)
    if model_version:
        stmt = stmt.where(Prediction.model_version == model_version)
    stmt = stmt.order_by(Prediction.target_timestamp.asc()).limit(limit)

    return db.scalars(stmt).all()
