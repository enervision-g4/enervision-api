import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import pytest

from app.models import Alert, MeasureRaw, Site
from app.routers import live
from app.security import create_access_token


@pytest.fixture(autouse=True)
def fast_poll(monkeypatch):
    """Le flux interroge la base toutes les 5s et envoie un battement de cœur
    toutes les 25s en production : inutile de faire attendre la suite de tests
    aussi longtemps."""
    monkeypatch.setattr(live, "POLL_INTERVAL_SECONDS", 0.05)
    monkeypatch.setattr(live, "HEARTBEAT_INTERVAL_SECONDS", 0.05)


def make_site(db_session, site_id="SITE001"):
    site = Site(
        site_id=site_id,
        site_type="factory",
        site_name="Usine Test",
        location="Lyon",
        capacity_kw=1000,
        status="active",
    )
    db_session.add(site)
    db_session.commit()
    return site


def make_reading(db_session, site_id, **overrides):
    defaults = dict(
        site_id=site_id,
        timestamp=datetime.now(timezone.utc),
        consumption_kw=42.0,
    )
    defaults.update(overrides)
    reading = MeasureRaw(**defaults)
    db_session.add(reading)
    db_session.commit()
    return reading


def make_alert(db_session, site_id, **overrides):
    defaults = dict(
        source_alert_id="ALR-TEST-1",
        site_id=site_id,
        timestamp=datetime.now(timezone.utc),
        severity="critical",
        type="overconsumption",
        message="Seuil dépassé",
    )
    defaults.update(overrides)
    alert = Alert(**defaults)
    db_session.add(alert)
    db_session.commit()
    return alert


def test_ws_readings_rejects_missing_token(client, db_session):
    make_site(db_session)

    # starlette ferme la connexion avant le handshake applicatif : la lib
    # cliente lève WebSocketDisconnect dès l'entrée dans le bloc `with`.
    try:
        with client.websocket_connect("/ws/readings?site_id=SITE001"):
            pass
        assert False, "la connexion aurait dû être refusée (token manquant)"
    except Exception:
        pass


def test_ws_readings_rejects_invalid_token(client, db_session):
    make_site(db_session)

    try:
        with client.websocket_connect("/ws/readings?site_id=SITE001&token=not-a-real-token"):
            pass
        assert False, "la connexion aurait dû être refusée (token invalide)"
    except Exception:
        pass


def test_ws_readings_pushes_rows_newer_than_since(client, db_session):
    """`since` = horodatage de la dernière mesure déjà chargée en REST par le
    dashboard : le flux reprend exactement là, sans trou ni rejeu."""
    make_site(db_session)
    now = datetime.now(timezone.utc)
    make_reading(db_session, "SITE001", timestamp=now - timedelta(minutes=10), consumption_kw=10.0)
    make_reading(db_session, "SITE001", timestamp=now, consumption_kw=99.0)
    token = create_access_token(subject="test-user")
    # quote() indispensable : le "+00:00" du fuseau est sinon décodé comme
    # une espace côté serveur (le client, lui, passe par URLSearchParams).
    since = quote((now - timedelta(minutes=5)).isoformat())

    url = f"/ws/readings?site_id=SITE001&token={token}&since={since}"
    with client.websocket_connect(url) as ws:
        message = ws.receive_json()
        assert message["type"] == "reading"
        # Seule la mesure postérieure à `since` est poussée : l'ancienne, déjà
        # affichée par le dashboard, ne l'est pas.
        assert message["data"]["consumption_kw"] == 99.0


def test_ws_readings_without_since_does_not_replay_history(client, db_session):
    """Sans `since`, le flux démarre au dernier horodatage en base : aucune
    donnée existante n'est rejouée (c'est ce rejeu qui saturait l'API et
    faisait clignoter le dashboard). Le premier message reçu est donc un
    battement de cœur, pas une mesure."""
    make_site(db_session)
    make_reading(db_session, "SITE001", consumption_kw=10.0)
    token = create_access_token(subject="test-user")

    with client.websocket_connect(f"/ws/readings?site_id=SITE001&token={token}") as ws:
        message = ws.receive_json()
        assert message["type"] == "heartbeat"


def test_ws_alerts_pushes_rows_newer_than_since(client, db_session):
    make_site(db_session)
    now = datetime.now(timezone.utc)
    make_alert(db_session, "SITE001", timestamp=now - timedelta(minutes=10), source_alert_id="ALR-1")
    make_alert(db_session, "SITE001", timestamp=now, source_alert_id="ALR-2", message="Nouvelle")
    token = create_access_token(subject="test-user")
    # quote() indispensable : le "+00:00" du fuseau est sinon décodé comme
    # une espace côté serveur (le client, lui, passe par URLSearchParams).
    since = quote((now - timedelta(minutes=5)).isoformat())

    with client.websocket_connect(f"/ws/alerts?token={token}&since={since}") as ws:
        message = ws.receive_json()
        assert message["type"] == "alert"
        assert message["data"]["message"] == "Nouvelle"


def test_ws_stops_polling_when_client_disconnects(client, db_session):
    """Régression : la boucle de lecture ne détectait le départ d'un client
    qu'au premier `send` en échec — donc jamais tant qu'aucune donnée neuve
    n'arrivait. Chaque navigation dans le dashboard laissait derrière elle une
    boucle qui continuait d'interroger la base (conteneur d'API à +50% de CPU
    au bout de quelques minutes d'utilisation)."""
    make_site(db_session)
    make_reading(db_session, "SITE001")
    token = create_access_token(subject="test-user")

    with client.websocket_connect(f"/ws/readings?site_id=SITE001&token={token}") as ws:
        ws.receive_json()  # la boucle tourne
        assert live._open_connections == 1

    deadline = time.monotonic() + 5
    while live._open_connections and time.monotonic() < deadline:
        time.sleep(0.02)
    assert live._open_connections == 0, "la boucle continue de tourner après le départ du client"


def test_ws_alerts_rejects_invalid_token(client, db_session):
    make_site(db_session)

    try:
        with client.websocket_connect("/ws/alerts?token=bad"):
            pass
        assert False, "la connexion aurait dû être refusée (token invalide)"
    except Exception:
        pass
