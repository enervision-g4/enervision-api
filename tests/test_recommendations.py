from datetime import datetime, timedelta, timezone

from app.models import Recommendation, Site


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


def make_recommendation(db_session, site_id, status="pending", **overrides):
    defaults = dict(
        site_id=site_id,
        prediction_id=None,
        timestamp=datetime.now(timezone.utc),
        action_description="Décaler la charge de 30 minutes",
        status=status,
    )
    defaults.update(overrides)
    recommendation = Recommendation(**defaults)
    db_session.add(recommendation)
    db_session.commit()
    return recommendation


def test_list_recommendations_empty(client, auth_headers):
    response = client.get("/api/v1/recommendations", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "page": 1, "limit": 25}


def test_list_recommendations_filters_by_site(client, db_session, auth_headers):
    make_site(db_session, "SITE001")
    make_site(db_session, "SITE002")
    make_recommendation(db_session, "SITE001")
    make_recommendation(db_session, "SITE002")

    response = client.get(
        "/api/v1/recommendations", params={"site_id": "SITE002"}, headers=auth_headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["site_id"] == "SITE002"


def test_list_recommendations_filters_by_status(client, db_session, auth_headers):
    make_site(db_session)
    make_recommendation(db_session, "SITE001", status="pending")
    make_recommendation(db_session, "SITE001", status="applied")

    response = client.get(
        "/api/v1/recommendations", params={"status": "applied"}, headers=auth_headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["status"] == "applied"


def test_list_recommendations_ordered_by_timestamp_desc_by_default(
    client, db_session, auth_headers
):
    make_site(db_session)
    now = datetime.now(timezone.utc)
    make_recommendation(db_session, "SITE001", timestamp=now - timedelta(hours=1))
    make_recommendation(db_session, "SITE001", timestamp=now)

    response = client.get(
        "/api/v1/recommendations", params={"site_id": "SITE001"}, headers=auth_headers
    )

    body = response.json()["items"]
    assert len(body) == 2
    assert body[0]["timestamp"] > body[1]["timestamp"]


def test_list_recommendations_sort_by_timestamp_asc(client, db_session, auth_headers):
    make_site(db_session)
    now = datetime.now(timezone.utc)
    make_recommendation(db_session, "SITE001", timestamp=now - timedelta(hours=1))
    make_recommendation(db_session, "SITE001", timestamp=now)

    response = client.get(
        "/api/v1/recommendations",
        params={"sort_by": "timestamp", "order": "asc"},
        headers=auth_headers,
    )

    body = response.json()["items"]
    assert len(body) == 2
    assert body[0]["timestamp"] < body[1]["timestamp"]


def test_list_recommendations_rejects_invalid_sort_by(client, auth_headers):
    response = client.get(
        "/api/v1/recommendations", params={"sort_by": "not_a_column"}, headers=auth_headers
    )

    assert response.status_code == 422


def test_list_recommendations_pagination(client, db_session, auth_headers):
    make_site(db_session)
    base = datetime.now(timezone.utc)
    for i in range(5):
        make_recommendation(db_session, "SITE001", timestamp=base - timedelta(minutes=i))

    page1 = client.get(
        "/api/v1/recommendations", params={"limit": 2, "page": 1}, headers=auth_headers
    ).json()
    page2 = client.get(
        "/api/v1/recommendations", params={"limit": 2, "page": 2}, headers=auth_headers
    ).json()

    assert page1["total"] == 5
    assert len(page1["items"]) == 2
    assert len(page2["items"]) == 2
    ids_page1 = {item["recommendation_id"] for item in page1["items"]}
    ids_page2 = {item["recommendation_id"] for item in page2["items"]}
    assert ids_page1.isdisjoint(ids_page2)


def test_recommendations_route_requires_auth(client):
    response = client.get("/api/v1/recommendations")

    assert response.status_code == 401
