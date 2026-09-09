import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt
from sqlalchemy import func, select
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
# nouvelles depuis le dernier envoi.
POLL_INTERVAL_SECONDS = 5

# Un WebSocket resté silencieux trop longtemps est coupé par les reverse-proxy
# (Traefik, nginx) et par certains navigateurs. Une trame "heartbeat" à
# intervalle régulier garde la connexion vivante sans réveiller le client
# (les vues ignorent les messages dont le `type` ne les concerne pas).
HEARTBEAT_INTERVAL_SECONDS = 25

# Plafond de connexions simultanées : chaque connexion = une boucle qui
# interroge la base. Sans plafond, un client qui reconnecte en boucle (ou
# plusieurs onglets laissés ouverts) fait grimper la charge CPU de l'API
# sans limite. 1013 = "try again later" (code WebSocket standard).
MAX_CONCURRENT_CONNECTIONS = 200
_open_connections = 0

# Nombre maximum de lignes poussées en un tour de boucle : borne le travail
# fait par itération quand un client se reconnecte après une longue coupure.
MAX_ROWS_PER_POLL = 200


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


def _latest_timestamp(db: Session, column, *filters):
    """Horodatage de la ligne la plus récente — une seule agrégation, pas un
    chargement de lignes."""
    stmt = select(func.max(column))
    for clause in filters:
        stmt = stmt.where(clause)
    return db.scalar(stmt)


async def _stream(
    websocket: WebSocket,
    db: Session,
    message_type: str,
    fetch_new,
):
    """Boucle commune aux deux routes : interroge `fetch_new(last_timestamp)`
    à intervalle régulier et pousse ce qui est nouveau.

    Point clé pour la charge CPU de l'API : on attend en parallèle un message
    du client (`websocket.receive()`), qui se résout par un
    `websocket.disconnect` dès que l'onglet est fermé ou que la vue change.
    Sans cette attente, un client parti n'était détecté qu'au premier `send`
    en échec — donc jamais tant qu'aucune donnée neuve n'arrivait : la boucle
    continuait d'interroger la base indéfiniment, et ces boucles fantômes
    s'accumulaient à chaque navigation dans le dashboard (cause du conteneur
    d'API à +50% de CPU).
    """
    global _open_connections

    if _open_connections >= MAX_CONCURRENT_CONNECTIONS:
        await websocket.close(code=1013)
        return

    await websocket.accept()
    _open_connections += 1
    receiver = asyncio.create_task(websocket.receive())
    silent_for = 0.0
    try:
        last_timestamp = None
        first_pass = True
        while True:
            payloads, last_timestamp = fetch_new(db, last_timestamp, first_pass)
            first_pass = False

            for payload in payloads:
                await websocket.send_json({"type": message_type, "data": payload})

            if payloads:
                silent_for = 0.0
            elif silent_for >= HEARTBEAT_INTERVAL_SECONDS:
                await websocket.send_json({"type": "heartbeat"})
                silent_for = 0.0

            done, _pending = await asyncio.wait({receiver}, timeout=POLL_INTERVAL_SECONDS)
            if receiver in done:
                try:
                    message = receiver.result()
                except Exception:
                    return  # connexion tombée : plus rien à pousser.
                if message.get("type") == "websocket.disconnect":
                    return
                # Message applicatif inattendu : on l'ignore mais on se remet
                # à l'écoute, sinon la détection de déconnexion serait perdue.
                receiver = asyncio.create_task(websocket.receive())
            else:
                silent_for += POLL_INTERVAL_SECONDS
    except WebSocketDisconnect:
        return
    finally:
        _open_connections -= 1
        receiver.cancel()


def _fetch_factory(model, schema, site_id, since):
    """Construit la fonction de lecture incrémentale utilisée par `_stream`.

    `since` vient du client : c'est l'horodatage de la donnée la plus récente
    qu'il a déjà chargée en REST. Le flux reprend donc exactement là où le
    chargement initial s'est arrêté — ni trou, ni rejeu. Sans `since`, on part
    du dernier horodatage en base : on ne pousse que du strictement nouveau.

    L'ancienne version partait de `last_timestamp = None` et rejouait tout
    l'historique par tranches croissantes de 500 lignes en repartant des plus
    ANCIENNES : à chaque connexion le dashboard recevait des centaines de
    lignes hors période affichée (graphique vide, liste d'alertes rechargée en
    boucle) et l'API rescannait la table toutes les 5 secondes.
    """

    def fetch(db: Session, last_timestamp, first_pass):
        if first_pass and last_timestamp is None:
            filters = [model.site_id == site_id] if site_id else []
            last_timestamp = since or _latest_timestamp(db, model.timestamp, *filters)
            if last_timestamp is None:
                # Table vide pour ce filtre : on repart de maintenant plutôt
                # que de rejouer l'historique au premier insert.
                last_timestamp = datetime.now(timezone.utc)

        stmt = select(model).where(model.timestamp > last_timestamp)
        if site_id:
            stmt = stmt.where(model.site_id == site_id)
        # Tri décroissant + limite : on prend les lignes les PLUS RÉCENTES,
        # puis on remet dans l'ordre chronologique pour l'envoi. Trier en
        # croissant comme avant faisait avancer le curseur d'un vieux paquet
        # à la fois quand le retard dépassait la limite.
        rows = db.scalars(stmt.order_by(model.timestamp.desc()).limit(MAX_ROWS_PER_POLL)).all()
        rows = list(reversed(rows))

        payloads = [schema.model_validate(row).model_dump(mode="json") for row in rows]
        next_timestamp = rows[-1].timestamp if rows else last_timestamp
        # Termine proprement la transaction de lecture à chaque tour : sans ce
        # commit elle resterait ouverte pendant toute la durée du WebSocket
        # ("idle in transaction" côté Postgres/TimescaleDB). Fait après
        # sérialisation : expire_on_commit expirerait sinon les objets lus.
        db.commit()
        return payloads, next_timestamp

    return fetch


@router.websocket("/ws/readings")
async def ws_readings(
    websocket: WebSocket,
    site_id: str,
    token: str = Query(...),
    since: datetime | None = None,
    db: Session = Depends(get_db),
):
    """Pousse chaque nouvelle mesure d'un site dès qu'elle apparaît en base."""
    if not _origin_allowed(websocket) or _subject_from_token(token) is None:
        await websocket.close(code=4401)
        return

    await _stream(websocket, db, "reading", _fetch_factory(MeasureRaw, ReadingOut, site_id, since))


@router.websocket("/ws/alerts")
async def ws_alerts(
    websocket: WebSocket,
    token: str = Query(...),
    site_id: str | None = None,
    since: datetime | None = None,
    db: Session = Depends(get_db),
):
    """Même principe que /ws/readings, pour les alertes."""
    if not _origin_allowed(websocket) or _subject_from_token(token) is None:
        await websocket.close(code=4401)
        return

    await _stream(websocket, db, "alert", _fetch_factory(Alert, AlertOut, site_id, since))
