from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Alert
from app.schemas import AlertPage
from app.security import get_current_subject

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])

# Colonnes autorisées pour sort_by — whitelist explicite plutôt que
# getattr(Alert, sort_by) pour ne jamais exposer un tri sur une colonne
# arbitraire à partir d'une chaîne fournie par le client.
SORTABLE_COLUMNS = {
    "timestamp": Alert.timestamp,
    "severity": Alert.severity,
    "site_id": Alert.site_id,
}


def _apply_filters(stmt, site_id, severity, start_time, end_time):
    """Applique les mêmes clauses where à n'importe quel select() portant sur
    Alert — que ce soit select(Alert), select(func.count()) ou un group_by."""
    if site_id:
        stmt = stmt.where(Alert.site_id == site_id)
    if severity:
        stmt = stmt.where(Alert.severity == severity)
    if start_time:
        stmt = stmt.where(Alert.timestamp >= start_time)
    if end_time:
        stmt = stmt.where(Alert.timestamp <= end_time)
    return stmt


@router.get("/summary", response_model=dict[str, int])
def alerts_summary(
    site_id: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    db: Session = Depends(get_db),
    _subject: str = Depends(get_current_subject),
):
    """Nombre d'alertes par sévérité, sur la période/site donnés — utilisé par
    la page d'accueil du dashboard pour le résumé "alertes par catégorie"
    sans avoir à paginer/charger toutes les alertes juste pour les compter.

    Déclarée avant `""` : `/summary` doit rester matchée avant qu'un futur
    `/{alert_id}` ne soit ajouté à ce router (aucun pour l'instant, mais
    évite le piège classique si quelqu'un en ajoute un plus tard).
    """
    stmt = _apply_filters(
        select(Alert.severity, func.count()).group_by(Alert.severity),
        site_id,
        None,
        start_time,
        end_time,
    )
    rows = db.execute(stmt).all()
    return {(severity or "inconnue"): count for severity, count in rows}


@router.get("", response_model=AlertPage)
def list_alerts(
    site_id: str | None = None,
    severity: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    sort_by: Literal["timestamp", "severity", "site_id"] = "timestamp",
    order: Literal["asc", "desc"] = "desc",
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    _subject: str = Depends(get_current_subject),
):
    """Alertes paginées, triables (`sort_by`/`order`) et filtrables par site,
    sévérité et plage horaire — consommées par la page /alertes du dashboard.

    Répond une enveloppe {items, total, page, limit} plutôt qu'une simple
    liste : le dashboard a besoin de `total` pour afficher le nombre de
    pages, ce qu'une liste brute ne permet pas de déduire.
    """
    total = db.scalar(
        _apply_filters(select(func.count()).select_from(Alert), site_id, severity, start_time, end_time)
    )

    column = SORTABLE_COLUMNS[sort_by]
    ordered_column = column.asc() if order == "asc" else column.desc()
    stmt = _apply_filters(select(Alert), site_id, severity, start_time, end_time)
    stmt = stmt.order_by(ordered_column).offset((page - 1) * limit).limit(limit)

    items = db.scalars(stmt).all()
    return AlertPage(items=items, total=total or 0, page=page, limit=limit)
