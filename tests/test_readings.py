from datetime import datetime, timedelta, timezone

from app.models import MeasureRaw, Site


def make_site(db_session, site_id="SITE001"):
    site = Site(
        site_id=site_id,
        site_type="office",
        site_name="Bureau Test",
        location="Paris",
        capacity_kw=200,
        status="active",
    )
    db_session.add(site)
    db_session.commit()
    return site


def make_reading(db_session, site_id, timestamp, **overrides):
    defaults = dict(
        site_id=site_id,
        timestamp=timestamp,
        consumption_kw=87.34,
        consumption_kwh=87.34,
        voltage_v=401.2,
        current_a=132.5,
        power_factor=0.923,
        temperature_celsius=22.1,
        humidity_percent=58.4,
        null_reasons=[],
        data_quality="good",
    )
    defaults.update(overrides)
    reading = MeasureRaw(**defaults)
    db_session.add(reading)
    db_session.commit()
    return reading


def test_list_readings_filters_by_site(client, db_session, auth_headers):
    make_site(db_session, "SITE001")
    make_site(db_session, "SITE002")
    now = datetime.now(timezone.utc)
    make_reading(db_session, "SITE001", now)
    make_reading(db_session, "SITE002", now)

    response = client.get("/api/v1/readings", params={"site_id": "SITE001"}, headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["site_id"] == "SITE001"


def test_list_readings_respects_time_window(client, db_session, auth_headers):
    make_site(db_session)
    now = datetime.now(timezone.utc)
    make_reading(db_session, "SITE001", now - timedelta(days=2))  # hors fenêtre par défaut (24h)
    make_reading(db_session, "SITE001", now)

    response = client.get("/api/v1/readings", params={"site_id": "SITE001"}, headers=auth_headers)

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_list_readings_respects_limit(client, db_session, auth_headers):
    make_site(db_session)
    now = datetime.now(timezone.utc)
    for i in range(5):
        make_reading(db_session, "SITE001", now - timedelta(minutes=i))

    response = client.get(
        "/api/v1/readings", params={"site_id": "SITE001", "limit": 2}, headers=auth_headers
    )

    assert response.status_code == 200
    assert len(response.json()) == 2


def test_range_hours_anchors_on_latest_data_not_wall_clock(client, db_session, auth_headers):
    """Régression : `range_hours` doit ancrer la fenêtre sur la donnée la plus
    récente réellement en base, pas sur l'horloge du serveur. Sans cet
    ancrage, un pipeline d'ingestion en retard (l'ETL écrit des données
    "vieilles" de quelques minutes/heures par rapport à l'horloge murale)
    rendait les fenêtres courtes (1h, 6h) systématiquement vides : la période
    [maintenant-1h, maintenant] ne recoupait alors aucune donnée réelle, même
    le jour où une fenêtre de 24h en montrait pourtant."""
    make_site(db_session)
    # Horodatage arbitrairement éloigné de "maintenant" (simule un fort
    # retard d'ingestion) : si la fenêtre était calculée depuis l'horloge du
    # serveur, cette donnée resterait invisible quelle que soit `range_hours`.
    lagged_timestamp = datetime.now(timezone.utc) - timedelta(hours=5)
    make_reading(db_session, "SITE001", lagged_timestamp, consumption_kw=42.0)

    response = client.get(
        "/api/v1/readings",
        params={"site_id": "SITE001", "range_hours": 1},
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["consumption_kw"] == 42.0


def test_readings_over_limit_are_sampled_across_full_window(client, db_session, auth_headers):
    """Régression : au-delà de `limit`, ne pas se contenter de garder les
    lignes les plus RÉCENTES. Avec un rythme d'ingestion élevé, cela ne
    montrait en réalité qu'une tranche de quelques heures et faisait
    disparaître tout le reste de la période demandée (ex. "7 jours" ne
    montrait que la dernière heure) — donnant l'impression à tort qu'il n'y
    avait aucune donnée les jours précédents. L'échantillonnage doit rester
    réparti sur toute la fenêtre, du point le plus ancien au plus récent."""
    make_site(db_session)
    now = datetime.now(timezone.utc)
    for i in range(20):
        make_reading(db_session, "SITE001", now - timedelta(days=7) + timedelta(hours=i * 8))

    response = client.get(
        "/api/v1/readings",
        params={"site_id": "SITE001", "range_hours": 24 * 7, "limit": 5},
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 5
    timestamps = [datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00")) for r in body]
    assert timestamps == sorted(timestamps)  # ordre chronologique préservé
    # Le point le plus ancien de la fenêtre doit être représenté (à la minute
    # près) : preuve que l'échantillonnage couvre toute la période, pas
    # seulement la fin.
    earliest_inserted = now - timedelta(days=7)
    assert abs((timestamps[0] - earliest_inserted).total_seconds()) < 60


def test_list_readings_keeps_null_values(client, db_session, auth_headers):
    """Conseil du sujet (API Mock doc) : ne jamais filtrer les NULL, les
    stocker/retourner tels quels avec data_quality."""
    make_site(db_session)
    make_reading(
        db_session,
        "SITE001",
        datetime.now(timezone.utc),
        consumption_kw=None,
        data_quality="critical",
        null_reasons=["network_loss"],
    )

    response = client.get("/api/v1/readings", params={"site_id": "SITE001"}, headers=auth_headers)

    assert response.status_code == 200
    body = response.json()[0]
    assert body["consumption_kw"] is None
    assert body["data_quality"] == "critical"
    assert body["null_reasons"] == ["network_loss"]
