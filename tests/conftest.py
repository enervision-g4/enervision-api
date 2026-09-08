"""Fixtures partagées.

Les tests tournent contre une vraie base Postgres/TimescaleDB (les types
UUID/ARRAY utilisés dans app/models.py sont spécifiques au dialecte
Postgres — impossible de les faire tourner sur SQLite en mémoire).

Par défaut ils visent une base "g4_db_test" séparée de la base de dev, sur
la même instance TimescaleDB locale (voir la conversation sur la mise en
place en local : docker compose -f compose/db.yml ... up -d). Créez-la une
fois avec :

    docker exec -it g4_db psql -U g4_app -d postgres -c "CREATE DATABASE g4_db_test;"

Chaque test tourne dans une transaction ouverte puis annulée (rollback) :
la base reste vide entre deux tests, pas besoin de la reset à la main.
"""

import os

# `app.config.settings` est un singleton construit à l'import du module (voir
# app/config.py) : 4 champs n'ont pas de valeur par défaut (DATABASE_URL,
# JWT_SECRET_KEY, API_USERNAME, API_PASSWORD_HASH), volontairement, pour
# qu'une configuration de déploiement incomplète échoue immédiatement plutôt
# que silencieusement. En local, un `.env` (non versionné) les fournit. En
# CI, il n'y a ni `.env` ni ces variables dans l'environnement du job — sans
# ce filet, `from app.database import ...` ci-dessous échoue à l'import avec
# une ValidationError avant même que le premier test ne démarre. Aucun test
# ne dépend de la vraie valeur de ces 4 champs (la base utilisée par les
# tests vient de TEST_DATABASE_URL ci-dessous, pas de DATABASE_URL ; les
# tests d'authentification substituent explicitement api_username/
# api_password_hash via monkeypatch) : `setdefault` avant l'import suffit,
# et ne touche pas à un `.env` réellement présent (les variables déjà
# exportées, y compris par `.env`, restent prioritaires).
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://g4_app:unused-in-tests@localhost:5432/g4_db_ci"
)
os.environ.setdefault("JWT_SECRET_KEY", "ci-test-secret-not-used-in-prod")
os.environ.setdefault("API_USERNAME", "ci-test-placeholder")
os.environ.setdefault("API_PASSWORD_HASH", "ci-test-placeholder")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.security import create_access_token

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://g4_app:dev_password@localhost:5432/g4_db_test",
)


@pytest.fixture(scope="session")
def engine():
    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def db_session(engine):
    """Une session par test, dans une transaction annulée à la fin
    (rollback) : aucun test ne voit les données d'un autre."""
    connection = engine.connect()
    transaction = connection.begin()
    SessionLocal = sessionmaker(bind=connection)
    session = SessionLocal()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db_session):
    """TestClient FastAPI, avec get_db substitué par la session de test."""

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers():
    """Un token JWT valide, généré directement (sans passer par
    /auth/login) : les tests de routes protégées n'ont pas besoin de
    connaître les identifiants du compte de service."""
    token = create_access_token(subject="test-user")
    return {"Authorization": f"Bearer {token}"}
