from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

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
    # Alternative à `start_time` pour le dashboard : "les N dernières heures
    # de données", ancrées sur la donnée la plus récente réellement en base
    # (voir plus bas) plutôt que sur l'horloge du navigateur. `start_time`
    # reste disponible tel quel pour un filtrage par dates absolues (ex. futur
    # sélecteur de plage personnalisée).
    range_hours: float | None = Query(default=None, gt=0),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    _subject: str = Depends(get_current_subject),
):
    def scoped(stmt):
        return stmt.where(MeasureRaw.site_id == site_id) if site_id else stmt

    if end_time is None:
        # Ancré sur `max(timestamp)` plutôt que sur l'horloge du serveur :
        # un retard d'ingestion (ETL en léger différé, horloges pas
        # parfaitement synchronisées entre le pipeline et l'API) suffisait à
        # rendre les fenêtres courtes (1h, 6h) totalement vides — la période
        # demandée [maintenant-1h, maintenant] ne recoupait alors aucune
        # donnée réelle, alors qu'une fenêtre large (24h) absorbait ce léger
        # retard sans que ça se voie. Avec cet ancrage, "la dernière heure"
        # veut dire "la dernière heure de données qui existent", pas "la
        # dernière heure d'horloge murale".
        end_time = db.scalar(scoped(select(func.max(MeasureRaw.timestamp))))
        end_time = end_time or datetime.now(timezone.utc)

    if range_hours is not None:
        start_time = end_time - timedelta(hours=range_hours)
    else:
        start_time = start_time or end_time - timedelta(hours=24)

    filtered = scoped(
        select(MeasureRaw).where(
            MeasureRaw.timestamp >= start_time,
            MeasureRaw.timestamp <= end_time,
        )
    )

    total = db.scalar(select(func.count()).select_from(filtered.subquery()))

    if not total or total <= limit:
        return db.scalars(filtered.order_by(MeasureRaw.timestamp.asc())).all()

    # Plus de lignes que `limit` sur la fenêtre demandée : sous-échantillonner
    # UNIFORMÉMENT sur toute la période plutôt que de garder les `limit`
    # lignes les plus récentes. Avec un rythme d'ingestion élevé, "garder les
    # plus récentes" revenait à ne montrer qu'une tranche de quelques heures
    # et à faire disparaître tout le reste de la période demandée (ex. "7
    # jours" ne montrait en réalité qu'une petite partie de la dernière
    # journée) — d'où l'impression à tort qu'il n'y avait aucune donnée les
    # jours précédents.
    stride = -(-total // limit)  # ceil(total / limit), sans dépendre de math
    row_number = func.row_number().over(order_by=MeasureRaw.timestamp.asc())
    numbered = filtered.add_columns(row_number.label("rn")).subquery()
    sampled = aliased(MeasureRaw, numbered)
    stmt = (
        select(sampled)
        .where((numbered.c.rn - 1) % stride == 0)
        .order_by(numbered.c.timestamp.asc())
    )
    return db.scalars(stmt).all()
