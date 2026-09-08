from datetime import UTC, datetime, timedelta

from app.models import Prediction, Site


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


def make_prediction(db_session, site_id, target_timestamp, **overrides):
    defaults = dict(
        site_id=site_id,
        target_timestamp=target_timestamp,
        timestamp=datetime.now(UTC),
        predicted_consumption_kw=650.0,
        threshold_kw=720.0,
        model_version="v1",
    )
    defaults.update(overrides)
    prediction = Prediction(**defaults)
    db_session.add(prediction)
    db_session.commit()
    return prediction


def test_list_predictions_empty(client, auth_headers):
    response = client.get("/api/v1/predictions", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == []


def test_list_predictions_filters_by_site(client, db_session, auth_headers):
    make_site(db_session, "SITE001")
    make_site(db_session, "SITE002")
    now = datetime.now(UTC)
    make_prediction(db_session, "SITE001", now + timedelta(hours=1))
    make_prediction(db_session, "SITE002", now + timedelta(hours=1))

    response = client.get(
        "/api/v1/predictions", params={"site_id": "SITE001"}, headers=auth_headers
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["site_id"] == "SITE001"


def test_list_predictions_filters_by_model_version(client, db_session, auth_headers):
    make_site(db_session)
    now = datetime.now(UTC)
    make_prediction(db_session, "SITE001", now + timedelta(hours=1), model_version="v1")
    make_prediction(db_session, "SITE001", now + timedelta(hours=2), model_version="v2")

    response = client.get(
        "/api/v1/predictions", params={"model_version": "v2"}, headers=auth_headers
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["model_version"] == "v2"


def test_list_predictions_ordered_by_target_timestamp_asc(client, db_session, auth_headers):
    """Ordre attendu pour tracer une courbe de prévision : horizon croissant,
    pas date de génération de la prédiction."""
    make_site(db_session)
    now = datetime.now(UTC)
    make_prediction(db_session, "SITE001", now + timedelta(hours=3))
    make_prediction(db_session, "SITE001", now + timedelta(hours=1))

    response = client.get(
        "/api/v1/predictions", params={"site_id": "SITE001"}, headers=auth_headers
    )

    body = response.json()
    assert len(body) == 2
    assert body[0]["target_timestamp"] < body[1]["target_timestamp"]


def test_list_predictions_keeps_only_the_latest_run_per_target_hour(
    client, db_session, auth_headers
):
    """Le service ml rejoue un lot a intervalle regulier et reecrit une
    prediction pour le meme creneau a chaque fois (l'historique des runs
    sert a mesurer sa justesse). Par defaut, une seule ligne par
    (site_id, target_timestamp) doit remonter : la plus recente."""
    make_site(db_session)
    now = datetime.now(UTC)
    same_target_hour = now + timedelta(hours=1)
    make_prediction(
        db_session,
        "SITE001",
        same_target_hour,
        timestamp=now - timedelta(hours=1),
        predicted_consumption_kw=500.0,
    )
    make_prediction(
        db_session,
        "SITE001",
        same_target_hour,
        timestamp=now,
        predicted_consumption_kw=650.0,
    )

    response = client.get(
        "/api/v1/predictions", params={"site_id": "SITE001"}, headers=auth_headers
    )

    body = response.json()
    assert len(body) == 1
    assert body[0]["predicted_consumption_kw"] == 650.0


def test_list_predictions_can_include_every_run_when_asked(client, db_session, auth_headers):
    make_site(db_session)
    now = datetime.now(UTC)
    same_target_hour = now + timedelta(hours=1)
    make_prediction(db_session, "SITE001", same_target_hour, timestamp=now - timedelta(hours=1))
    make_prediction(db_session, "SITE001", same_target_hour, timestamp=now)

    response = client.get(
        "/api/v1/predictions",
        params={"site_id": "SITE001", "latest_only": False},
        headers=auth_headers,
    )

    assert len(response.json()) == 2


def test_predictions_route_requires_auth(client):
    response = client.get("/api/v1/predictions")

    assert response.status_code == 401
