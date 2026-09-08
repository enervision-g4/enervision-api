from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.database import get_db
from app.models import Prediction
from app.schemas import PredictionOut
from app.security import get_current_subject

router = APIRouter(prefix="/api/v1/predictions", tags=["predictions"])


@router.get("", response_model=list[PredictionOut])
def list_predictions(
    site_id: str | None = None,
    model_version: str | None = None,
    latest_only: bool = True,
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    _subject: str = Depends(get_current_subject),
):
    """Prédictions de consommation issues du modèle ML.

    Triées par target_timestamp (l'horizon prédit) croissant : c'est
    l'ordre attendu pour tracer une courbe de prévision sur le dashboard,
    à ne pas confondre avec `timestamp` qui est la date de génération de
    la prédiction.

    latest_only (True par défaut) ne garde qu'une ligne par (site_id,
    target_timestamp) : le service ml rejoue un lot à intervalle régulier
    et réécrit une prédiction pour le même créneau à chaque fois (l'historique
    des runs sert à mesurer sa justesse dans le temps). Sans ce filtre, le
    dashboard afficherait toutes les prédictions successives du même
    créneau au lieu de la plus récente.
    """
    stmt = select(Prediction)
    if site_id:
        stmt = stmt.where(Prediction.site_id == site_id)
    if model_version:
        stmt = stmt.where(Prediction.model_version == model_version)

    if latest_only:
        # `DISTINCT ON` n'existe que sur Postgres (silencieusement ignoré
        # ailleurs, cf. SADeprecationWarning) : row_number() + partition_by
        # fait la même chose (garder la ligne la plus récente par groupe
        # site_id/target_timestamp) en restant portable — SQLite (tests
        # unitaires) y compris. Même motif que le sous-échantillonnage de
        # GET /api/v1/readings (app/routers/readings.py).
        row_number = func.row_number().over(
            partition_by=(Prediction.site_id, Prediction.target_timestamp),
            order_by=Prediction.timestamp.desc(),
        )
        numbered = stmt.add_columns(row_number.label("rn")).subquery()
        latest = aliased(Prediction, numbered)
        stmt = (
            select(latest)
            .where(numbered.c.rn == 1)
            .order_by(numbered.c.target_timestamp.asc())
        )
    else:
        stmt = stmt.order_by(Prediction.target_timestamp.asc())

    stmt = stmt.limit(limit)

    return db.scalars(stmt).all()
