# enervision-api

API sécurisée (FastAPI) exposant au dashboard les données de consommation
énergétique stockées dans TimescaleDB (voir `enervision-devops`) : sites,
mesures, alertes, prédictions et recommandations. Authentification par JWT
(`POST /auth/login`), plus deux endpoints WebSocket pour le temps réel.

📖 **Documentation complète : [`docs/`](docs/README.md)** — architecture, modèle de
données, routes, WebSocket, sécurité, configuration, déploiement, tests. Ce README ne
donne que les points essentiels pour démarrer ; `docs/` explique le *pourquoi* derrière
chaque choix.

## Lancer en local

Dépendances gérées par [uv](https://docs.astral.sh/uv/) (même outillage que
`enervision-etl`) : pas de `venv`/`pip` manuels, `uv.lock` fige les versions
exactes.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

uv sync
cp .env.example .env   # renseigner DATABASE_URL vers une instance TimescaleDB
uv run uvicorn app.main:app --reload --port 3000
```

`uv sync` télécharge Python 3.14 si la machine ne l'a pas, crée `.venv/` et
installe les versions exactes figées dans `uv.lock`.

Documentation interactive : http://localhost:3000/docs

## Développement

```bash
uv run pytest              # suite de tests unitaires (SQLite en mémoire, aucune base externe)
uv run ruff check app tests
uv run mypy
```

Détail de la stratégie de test : [docs/09-tests-et-qualite.md](docs/09-tests-et-qualite.md).

## Routes en un coup d'œil

Toutes les routes `/api/v1/*` exigent un token JWT (`Authorization: Bearer
<token>`), obtenu via `POST /auth/login`. Détail complet (paramètres, formats
de réponse, exemples) : [docs/04-routes-rest.md](docs/04-routes-rest.md).

| Route | Description |
| --- | --- |
| `GET /health` | Healthcheck (non protégé), utilisé par Docker |
| `POST /auth/login` | Authentification (compte de service), retourne un JWT |
| `GET /api/v1/sites` | Liste des sites |
| `GET /api/v1/sites/{site_id}` | Détail d'un site |
| `GET /api/v1/readings` | Historique des mesures (`site_id`, `start_time`, `end_time`, `limit`) |
| `GET /api/v1/alerts` | Alertes paginées, triables, filtrables — réponse `{items, total, page, limit}` |
| `GET /api/v1/alerts/summary` | Nombre d'alertes par sévérité |
| `GET /api/v1/predictions` | Prédictions de consommation, triées par horizon croissant |
| `GET /api/v1/recommendations` | Recommandations d'actions correctives, les plus récentes d'abord |

## Temps réel (WebSocket)

`GET /ws/readings` et `GET /ws/alerts` poussent respectivement chaque nouvelle
mesure/alerte dès qu'elle apparaît en base (poll interne toutes les 5s, ne pousse que
les lignes nouvelles). Mécanisme complet, contrat client (`since`, heartbeat, détection
de déconnexion, plafond de connexions) et le bug CPU corrigé qui l'a fait évoluer :
[docs/05-temps-reel-websocket.md](docs/05-temps-reel-websocket.md).

## Structure

```
app/
├── main.py            # point d'entrée FastAPI, montage des routers
├── config.py          # settings (pydantic-settings) depuis l'environnement
├── database.py        # engine SQLAlchemy + dépendance get_db
├── models.py          # modèles ORM (miroir des tables créées par
│                         enervision-devops/db/init/002_create_tables.sql)
├── schemas.py         # schémas Pydantic (réponses API)
├── security.py        # JWT (création/validation de token) + hachage Argon2id
└── routers/
    ├── auth.py             # POST /auth/login
    ├── sites.py            # GET /api/v1/sites, GET /api/v1/sites/{site_id}
    ├── readings.py         # GET /api/v1/readings
    ├── alerts.py           # GET /api/v1/alerts
    ├── predictions.py      # GET /api/v1/predictions
    ├── recommendations.py  # GET /api/v1/recommendations
    └── live.py             # GET /ws/readings, GET /ws/alerts (WebSocket)
```

Détail architecture et raisonnement : [docs/02-architecture.md](docs/02-architecture.md)
et [docs/03-modele-de-donnees.md](docs/03-modele-de-donnees.md).

## Secrets

`.env` n'est **jamais commité** : en local il contient les valeurs de dev, en
déploiement ces mêmes variables (`JWT_SECRET_KEY`, `API_USERNAME`,
`API_PASSWORD_HASH`, `DATABASE_URL`...) viennent du secret GitHub
`ENV_FILE_CONTENTS` de l'environnement ciblé (`onprem-dev` / `onprem-prod`).
`API_PASSWORD_HASH` est un hash Argon2id, jamais le mot de passe en clair.

`CORS_ALLOWED_ORIGINS` doit être l'URL exacte (protocole+hôte+port) depuis laquelle le
dashboard est servi, sinon le navigateur bloque tous ses appels à l'API. Détail complet :
[docs/06-securite.md](docs/06-securite.md) et [docs/07-configuration.md](docs/07-configuration.md).

## Déploiement

L'image Docker est construite en deux étages (dépendances `uv` puis runtime minimal),
poussée sur `ghcr.io/enervision-g4/enervision-api`, puis le déploiement effectif est
délégué au workflow réutilisable de `enervision-devops` (`deploy.yml`, `compose/api.yml`)
sur le serveur on-premise, via un runner self-hosted. Trajet complet, pourquoi cette
centralisation, et détail du workflow pas à pas :
[docs/08-deploiement-et-flux-devops.md](docs/08-deploiement-et-flux-devops.md).
