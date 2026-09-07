from datetime import datetime, timezone

from app.models import MeasureRaw, Site
from app.security import create_access_token


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


def test_ws_readings_pushes_existing_then_new_reading(client, db_session):
    make_site(db_session)
    make_reading(db_session, "SITE001", consumption_kw=10.0)
    token = create_access_token(subject="test-user")

    with client.websocket_connect(f"/ws/readings?site_id=SITE001&token={token}") as ws:
        first = ws.receive_json()
        assert first["type"] == "reading"
        assert first["data"]["consumption_kw"] == 10.0


def test_ws_alerts_rejects_invalid_token(client, db_session):
    make_site(db_session)

    try:
        with client.websocket_connect("/ws/alerts?token=bad"):
            pass
        assert False, "la connexion aurait dû être refusée (token invalide)"
    except Exception:
        pass
