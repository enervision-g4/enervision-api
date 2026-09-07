import asyncio

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Alert, MeasureRaw
from app.schemas import AlertOut, ReadingOut

router = APIRouter(tags=["live"])

# Le WebSocket ne peut pas être notifié en vrai push : l'ETL/les consumers
# Kafka écrivent directement en base sans passer par l'API, il n'y a pas de
# bus d'événements côté API pour se brancher dessus. On interroge donc la
# base à intervalle court et on ne pousse au client que les lignes réellement
# nouvelles depuis le dernier envoi — pour le dashboard, indiscernable d'un
# vrai push : aucune requête inutile quand rien n'a changé, un seul nouveau
# point ajouté à la volée sinon, sans le flash de rechargement du polling
# HTTP précédent.
POLL_INTERVAL_SECONDS = 5


def _subject_from_token(token: str) -> str | None:
    """Variante de security.get_current_subject utilisable hors d'une requête
    HTTP classique : un WebSocket natif ne peut pas poser de header
    Authorization (limitation des navigateurs), le token JWT est donc passé
    en query string (?token=...)."""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return payload.get("sub")
    except JWTError:
        return None


def _origin_allowed(websocket: WebSocket) -> bool:
    """CORSMiddleware ne protège pas les routes WebSocket : on revalide donc
    l'origine nous-mêmes, avec la même liste que le CORS HTTP."""
    origin = websocket.headers.get("origin")
    if origin is None:
        return True  # client non-navigateur (tests, wscat) : pas d'Origin à valider.
    return origin in settings.cors_allowed_origins_list


@router.websocket("/ws/readings")
async def ws_readings(
    websocket: WebSocket,
    site_id: str,
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    """Pousse chaque nouvelle mesure d'un site dès qu'elle apparaît en base."""
    if not _origin_allowed(websocket) or _subject_from_token(token) is None:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    last_timestamp = None
    try:
        while True:
            stmt = select(MeasureRaw).where(MeasureRaw.site_id == site_id)
            if last_timestamp is not None:
                stmt = stmt.where(MeasureRaw.timestamp > last_timestamp)
            stmt = stmt.order_by(MeasureRaw.timestamp.asc()).limit(500)
            new_rows = db.scalars(stmt).all()
            payloads = [ReadingOut.model_validate(row).model_dump(mode="json") for row in new_rows]
            next_timestamp = new_rows[-1].timestamp if new_rows else last_timestamp
            # Termine proprement la transaction de lecture à chaque tour : sous
            # Postgres (READ COMMITTED) chaque requête voit déjà les derniers
            # commits d'autres connexions, mais sans ce commit la transaction
            # resterait ouverte pendant toute la durée du WebSocket — mauvais
            # pour Postgres/TimescaleDB ("idle in transaction"). Fait après
            # sérialisation : expire_on_commit expirerait sinon les objets
            # qu'on vient de lire.
            db.commit()
            last_timestamp = next_timestamp

            for payload in payloads:
                await websocket.send_json({"type": "reading", "data": payload})

            await asyncio.sleep(POLL_INTERVAL_SECONDS)
    except WebSocketDisconnect:
        return


@router.websocket("/ws/alerts")
async def ws_alerts(
    websocket: WebSocket,
    token: str = Query(...),
    site_id: str | None = None,
    db: Session = Depends(get_db),
):
    """Même principe que /ws/readings, pour les alertes."""
    if not _origin_allowed(websocket) or _subject_from_token(token) is None:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    last_timestamp = None
    try:
        while True:
            stmt = select(Alert)
            if site_id:
                stmt = stmt.where(Alert.site_id == site_id)
            if last_timestamp is not None:
                stmt = stmt.where(Alert.timestamp > last_timestamp)
            stmt = stmt.order_by(Alert.timestamp.asc()).limit(200)
            new_rows = db.scalars(stmt).all()
            payloads = [AlertOut.model_validate(row).model_dump(mode="json") for row in new_rows]
            next_timestamp = new_rows[-1].timestamp if new_rows else last_timestamp
            db.commit()
            last_timestamp = next_timestamp

            for payload in payloads:
                await websocket.send_json({"type": "alert", "data": payload})

            await asyncio.sleep(POLL_INTERVAL_SECONDS)
    except WebSocketDisconnect:
        return
