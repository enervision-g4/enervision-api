import uuid
from datetime import datetime, timezone

from app.models import Alert, Site


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


def make_alert(db_session, site_id, severity="critical", **overrides):
    raised_at = overrides.pop("timestamp", datetime.now(timezone.utc))
    defaults = dict(
        source_alert_id=f"ALR-{site_id}-{raised_at.timestamp():.6f}",
        site_id=site_id,
        timestamp=raised_at,
        severity=severity,
        type="outage",
        message="Risque de surcharge",
        value_kw=812.5,
        threshold_kw=720.0,
    )
    defaults.update(overrides)
    alert = Alert(**defaults)
    db_session.add(alert)
    db_session.commit()
    return alert


def test_list_alerts_empty(client, auth_headers):
    response = client.get("/api/v1/alerts", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == []


def test_list_alerts_filters_by_severity(client, db_session, auth_headers):
    make_site(db_session)
    make_alert(db_session, "SITE001", severity="critical")
    make_alert(db_session, "SITE001", severity="low")

    response = client.get("/api/v1/alerts", params={"severity": "critical"}, headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["severity"] == "critical"


def test_list_alerts_filters_by_site(client, db_session, auth_headers):
    make_site(db_session, "SITE001")
    make_site(db_session, "SITE002")
    make_alert(db_session, "SITE001")
    make_alert(db_session, "SITE002")

    response = client.get("/api/v1/alerts", params={"site_id": "SITE002"}, headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["site_id"] == "SITE002"


def test_list_alerts_exposes_both_identifiers(client, db_session, auth_headers):
    make_site(db_session)
    make_alert(db_session, "SITE001")

    response = client.get("/api/v1/alerts", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    # alert_id est l'identifiant technique, source_alert_id celui de l'API source.
    # Les deux doivent traverser la sérialisation : un UUID typé en str la faisait
    # échouer et rendait la route inutilisable dès qu'une alerte existait.
    uuid.UUID(body[0]["alert_id"])
    assert body[0]["source_alert_id"].startswith("ALR-SITE001-")
