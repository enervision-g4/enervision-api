"""Fixtures partagées.

Tests unitaires : la base est un SQLite en mémoire, recréé à chaque session
de test à partir des modèles SQLAlchemy (`Base.metadata.create_all`), sans
aucune base externe à démarrer ou provisionner. Les modèles utilisent des
types cross-dialecte (`Uuid`, `ARRAY(...).with_variant(JSON(), "sqlite")` —
voir app/models.py) : ce qui tourne ici exerce la même logique applicative
(filtres, tri, pagination, fenêtrage) qu'en production sur Postgres/
TimescaleDB, sans dépendre de son dialecte SQL spécifique.

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
# ne dépend de la vraie valeur de ces 4 champs (la base de test est un SQLite
# en mémoire, indépendant de DATABASE_URL ; les tests d'authentification
# substituent explicitement api_username/api_password_hash via monkeypatch) :
# `setdefault` avant l'import suffit, et ne touche pas à un `.env` réellement
# présent (les variables déjà exportées, y compris par `.env`, restent
# prioritaires).
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
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.security import create_access_token

# StaticPool : une seule connexion SQLite partagée par tout le fixture
# "engine", nécessaire pour qu'une base ":memory:" survive entre les
# `engine.connect()` successifs de `db_session` (sans ça, chaque connexion
# verrait une base fraîche et vide, la précédente ayant disparu avec elle).
TEST_DATABASE_URL = "sqlite+pysqlite:///:memory:"


@pytest.fixture(scope="session")
def engine():
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
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
