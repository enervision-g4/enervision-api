# Tests et qualité

Ce document explique comment vérifier que le code de `enervision-api` fonctionne
correctement, et ce que la CI contrôle **avant** même qu'une image Docker ne soit
construite (voir [08-deploiement-et-flux-devops.md](08-deploiement-et-flux-devops.md)).

## Trois vérifications, trois commandes

```bash
uv run pytest          # les tests automatiques
uv run ruff check .     # style et erreurs évidentes
uv run mypy app         # cohérence des types
```

Les trois doivent passer avant qu'une pull request ne soit fusionnée. C'est ce que la CI
exécute à chaque push, dans cet ordre-là — pas de raison de builder une image Docker si
les tests échouent déjà.

## Les tests : base SQLite en mémoire, pas PostgreSQL

En production, `enervision-api` lit une base **TimescaleDB** (PostgreSQL). Mais les
tests n'en dépendent pas : `tests/conftest.py` fait tourner chaque test contre une base
**SQLite en mémoire**, créée et détruite à la volée.

```python
# tests/conftest.py (extrait, simplifié)
import os
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
# ... autres variables requises par Settings, avant que app.config ne soit importé

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
```

Deux détails qui ne sautent pas aux yeux :

- **Les variables d'environnement sont posées avant l'import de `app.config`.**
  `Settings` (voir [07-configuration.md](07-configuration.md)) lit l'environnement au
  moment de l'import — si `conftest.py` important `app.main` avant d'avoir positionné
  `DATABASE_URL`, `Settings()` lèverait une erreur de validation ou pointerait vers une
  base qui n'existe pas.
- **`StaticPool` avec `check_same_thread=False`.** SQLite en mémoire n'existe que dans
  la connexion qui l'a créée : le pool par défaut de SQLAlchemy ouvrirait une nouvelle
  connexion (donc une nouvelle base vide) à chaque requête. `StaticPool` force une
  connexion unique, réutilisée partout — c'est ce qui permet à un test de lire ce qu'un
  autre a écrit dans la même base en mémoire.

Ce choix a un prix documenté ailleurs : SQLite n'a pas de type `ARRAY` ni de fuseau
horaire strict, d'où `_STRING_ARRAY` et `_UtcTimestamp` dans `app/models.py` (voir
[03-modele-de-donnees.md](03-modele-de-donnees.md)) — ces deux types existent
**uniquement** pour que les mêmes modèles ORM fonctionnent sur SQLite en test et sur
PostgreSQL en production, sans dupliquer les modèles.

## Isolation : rollback après chaque test

```python
@pytest.fixture
def db_session():
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()
```

Chaque test tourne dans sa propre transaction, annulée (`rollback`) à la fin — jamais de
`commit` réel. Un test qui crée un site n'affecte donc jamais le suivant : pas besoin de
nettoyer la base entre deux tests, pas de risque qu'un test dépende de l'ordre
d'exécution des autres.

## Ce que les fichiers de test couvrent

| Fichier | Ce qu'il vérifie |
|---|---|
| `test_health.py` | `/health` répond bien, sans dépendre de la base. |
| `test_auth.py` | `POST /auth/login` accepte les bons identifiants, rejette les mauvais, émet un JWT valide. |
| `test_sites.py` | Liste des sites, format de sortie (`SiteOut`). |
| `test_readings.py` | Fenêtrage par `range_hours` ancré sur `MAX(timestamp)`, sous-échantillonnage uniforme, filtrage par site. |
| `test_alerts.py` | Pagination (`AlertPage`), tri via `SORTABLE_COLUMNS`, endpoint `/summary`. |
| `test_predictions.py` | `latest_only` (un seul lot par site via `row_number()` partitionné), filtrage par site. |
| `test_recommendations.py` | Même schéma de pagination qu'`alerts.py`. |
| `test_live.py` | Le WebSocket accepte une connexion authentifiée, pousse les nouvelles lignes, et surtout : `test_ws_stops_polling_when_client_disconnects`. |

### Le test qui vérifie le bug CPU corrigé

`test_ws_stops_polling_when_client_disconnects` (dans `test_live.py`) existe pour une
raison précise, détaillée dans
[05-temps-reel-websocket.md](05-temps-reel-websocket.md) : une première version du
endpoint `/ws/readings` ne détectait une déconnexion client qu'**après** l'intervalle de
polling suivant, ce qui pouvait laisser une boucle tourner inutilement en tâche de fond.
Le correctif attend en parallèle `websocket.receive()` **et** le prochain poll, pour
réagir à la déconnexion immédiatement plutôt qu'au prochain tick. Ce test simule une
déconnexion côté client et vérifie que la boucle serveur s'arrête bien sans attendre le
polling suivant — sans lui, une régression sur ce point precis ne serait détectée qu'en
production, sous forme de connexions WebSocket fantômes qui s'accumulent.

## `ruff` : style et pièges courants

`ruff check .` remplace à la fois un linter de style (imports inutilisés, lignes trop
longues) et une partie de ce que `flake8`/`pylint` couvriraient séparément — plus rapide,
un seul outil à configurer. La configuration vit dans `pyproject.toml` :

```toml
[tool.ruff]
line-length = 100
target-version = "py314"
```

## `mypy` : cohérence des types, avec le plugin Pydantic

```toml
[tool.mypy]
plugins = ["pydantic.mypy"]
```

Le plugin `pydantic.mypy` est nécessaire car Pydantic génère certains attributs et
validations dynamiquement (`model_validate`, alias de champs) — sans le plugin, `mypy`
signalerait des erreurs de type sur du code Pydantic parfaitement valide, faute de
comprendre ce que la métaclasse `BaseModel` fait réellement.

## Pourquoi ça vient avant le déploiement

Rappel du lien avec [08-deploiement-et-flux-devops.md](08-deploiement-et-flux-devops.md) :
la CI (`ruff` + `mypy` + `pytest`) s'exécute **avant** l'étape de build d'image Docker.
Une image n'est construite, poussée sur GHCR et proposée au déploiement que si ces trois
vérifications passent — évite de déployer un code qui ne compile pas ses propres types
ou casse un test existant, sans avoir à attendre qu'un humain le remarque en prod.
