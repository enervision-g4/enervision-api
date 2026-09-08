import uuid
from datetime import UTC, datetime, timedelta

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
    raised_at = overrides.pop("timestamp", datetime.now(UTC))
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
    body = response.json()
    assert body == {"items": [], "total": 0, "page": 1, "limit": 20}


def test_list_alerts_filters_by_severity(client, db_session, auth_headers):
    make_site(db_session)
    make_alert(db_session, "SITE001", severity="critical")
    make_alert(db_session, "SITE001", severity="low")

    response = client.get("/api/v1/alerts", params={"severity": "critical"}, headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["severity"] == "critical"


def test_list_alerts_filters_by_site(client, db_session, auth_headers):
    make_site(db_session, "SITE001")
    make_site(db_session, "SITE002")
    make_alert(db_session, "SITE001")
    make_alert(db_session, "SITE002")

    response = client.get("/api/v1/alerts", params={"site_id": "SITE002"}, headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["site_id"] == "SITE002"


def test_list_alerts_filters_by_time_range(client, db_session, auth_headers):
    make_site(db_session)
    now = datetime.now(UTC)
    make_alert(db_session, "SITE001", timestamp=now - timedelta(days=5))
    make_alert(db_session, "SITE001", timestamp=now)

    response = client.get(
        "/api/v1/alerts",
        params={"start_time": (now - timedelta(hours=1)).isoformat()},
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1


def test_list_alerts_exposes_both_identifiers(client, db_session, auth_headers):
    make_site(db_session)
    make_alert(db_session, "SITE001")

    response = client.get("/api/v1/alerts", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()["items"]
    # alert_id est l'identifiant technique, source_alert_id celui de l'API source.
    # Les deux doivent traverser la sérialisation : un UUID typé en str la faisait
    # échouer et rendait la route inutilisable dès qu'une alerte existait.
    uuid.UUID(body[0]["alert_id"])
    assert body[0]["source_alert_id"].startswith("ALR-SITE001-")


def test_list_alerts_pagination(client, db_session, auth_headers):
    make_site(db_session)
    base = datetime.now(UTC)
    for i in range(5):
        make_alert(db_session, "SITE001", timestamp=base - timedelta(minutes=i))

    params1 = {"limit": 2, "page": 1}
    params2 = {"limit": 2, "page": 2}
    page1 = client.get("/api/v1/alerts", params=params1, headers=auth_headers).json()
    page2 = client.get("/api/v1/alerts", params=params2, headers=auth_headers).json()

    assert page1["total"] == 5
    assert len(page1["items"]) == 2
    assert len(page2["items"]) == 2
    # Pas de chevauchement entre les pages.
    ids_page1 = {item["alert_id"] for item in page1["items"]}
    ids_page2 = {item["alert_id"] for item in page2["items"]}
    assert ids_page1.isdisjoint(ids_page2)


def test_list_alerts_sort_by_severity_asc(client, db_session, auth_headers):
    make_site(db_session)
    make_alert(db_session, "SITE001", severity="low")
    make_alert(db_session, "SITE001", severity="critical")

    response = client.get(
        "/api/v1/alerts", params={"sort_by": "severity", "order": "asc"}, headers=auth_headers
    )

    body = response.json()
    severities = [item["severity"] for item in body["items"]]
    assert severities == sorted(severities)


def test_list_alerts_rejects_invalid_sort_by(client, auth_headers):
    response = client.get(
        "/api/v1/alerts", params={"sort_by": "not_a_column"}, headers=auth_headers
    )

    assert response.status_code == 422


def test_alerts_route_requires_auth(client):
    response = client.get("/api/v1/alerts")

    assert response.status_code == 401


def test_alerts_summary_groups_by_severity(client, db_session, auth_headers):
    make_site(db_session)
    make_alert(db_session, "SITE001", severity="critical")
    make_alert(db_session, "SITE001", severity="critical")
    make_alert(db_session, "SITE001", severity="low")

    response = client.get("/api/v1/alerts/summary", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {"critical": 2, "low": 1}


def test_alerts_summary_filters_by_site(client, db_session, auth_headers):
    make_site(db_session, "SITE001")
    make_site(db_session, "SITE002")
    make_alert(db_session, "SITE001", severity="critical")
    make_alert(db_session, "SITE002", severity="low")

    response = client.get(
        "/api/v1/alerts/summary", params={"site_id": "SITE001"}, headers=auth_headers
    )

    assert response.status_code == 200
    assert response.json() == {"critical": 1}


def test_alerts_summary_requires_auth(client):
    response = client.get("/api/v1/alerts/summary")

    assert response.status_code == 401
