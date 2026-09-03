from app.models import Site


def make_site(db_session, **overrides):
    defaults = dict(
        site_id="SITE001",
        site_type="office",
        site_name="Bureau Paris La Défense",
        location="Paris, France",
        capacity_kw=200,
        status="active",
    )
    defaults.update(overrides)
    site = Site(**defaults)
    db_session.add(site)
    db_session.commit()
    return site


def test_list_sites_empty(client, auth_headers):
    response = client.get("/api/v1/sites", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == []


def test_list_sites_returns_seeded_sites(client, db_session, auth_headers):
    make_site(db_session)
    make_site(db_session, site_id="SITE002", site_name="Usine Lyon Vénissieux")

    response = client.get("/api/v1/sites", headers=auth_headers)

    assert response.status_code == 200
    site_ids = {site["site_id"] for site in response.json()}
    assert site_ids == {"SITE001", "SITE002"}


def test_get_site_by_id(client, db_session, auth_headers):
    make_site(db_session)

    response = client.get("/api/v1/sites/SITE001", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["site_name"] == "Bureau Paris La Défense"
    assert body["capacity_kw"] == 200


def test_get_site_not_found(client, auth_headers):
    response = client.get("/api/v1/sites/UNKNOWN", headers=auth_headers)

    assert response.status_code == 404
