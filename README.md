# enervision-api

API sécurisée (FastAPI) exposant au dashboard les données de consommation
énergétique stockées dans TimescaleDB (voir `enervision-devops`) : sites,
mesures, alertes, prédictions et recommandations. Authentification par JWT
(`POST /auth/login`).

## Lancer en local

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # renseigner DATABASE_URL vers une instance TimescaleDB
uvicorn app.main:app --reload --port 3000
```

Documentation interactive : http://localhost:3000/docs

## Routes

Toutes les routes `/api/v1/*` exigent un token JWT (`Authorization: Bearer
<token>`), obtenu via `POST /auth/login`.

| Route | Description |
| --- | --- |
| `GET /health` | Healthcheck (non protégé), utilisé par Docker |
| `POST /auth/login` | Authentification (compte de service), retourne un JWT |
| `GET /api/v1/sites` | Liste des sites |
| `GET /api/v1/sites/{site_id}` | Détail d'un site |
| `GET /api/v1/readings` | Historique des mesures (`site_id`, `start_time`, `end_time`, `limit`) |
| `GET /api/v1/alerts` | Alertes (`site_id`, `severity`) |
| `GET /api/v1/predictions` | Prédictions de consommation (`site_id`, `model_version`, `limit`), triées par horizon (`target_timestamp`) croissant |
| `GET /api/v1/recommendations` | Recommandations d'actions correctives (`site_id`, `status`, `limit`), les plus récentes d'abord |

## Structure

```
app/
├── main.py            # point d'entrée FastAPI, montage des routers
├── config.py          # settings (pydantic-settings) depuis l'environnement
├── database.py        # engine SQLAlchemy + dépendance get_db
├── models.py          # modèles ORM (miroir des tables créées par
│                         enervision-devops/db/init/002_create_tables.sql)
├── schemas.py         # schémas Pydantic (réponses API)
├── security.py        # JWT (création/validation de token)
└── routers/
    ├── auth.py             # POST /auth/login
    ├── sites.py            # GET /api/v1/sites, GET /api/v1/sites/{site_id}
    ├── readings.py         # GET /api/v1/readings
    ├── alerts.py           # GET /api/v1/alerts
    ├── predictions.py      # GET /api/v1/predictions
    └── recommendations.py  # GET /api/v1/recommendations
```

## Secrets

`.env` n'est **jamais commité** (voir `.gitignore`) : en local il contient
les valeurs de dev, en déploiement ces mêmes variables (`JWT_SECRET_KEY`,
`API_USERNAME`, `API_PASSWORD_HASH`, `DATABASE_URL`...) viennent du secret
GitHub `ENV_FILE_CONTENTS` de l'environnement ciblé (`onprem-dev` /
`onprem-prod`, un secret distinct par stage — voir
`enervision-devops/envs/*.env.example` et le README de `enervision-devops`).
`API_PASSWORD_HASH` est un hash Argon2id, jamais le mot de passe en clair
(générateur : `python -c "from app.security import hash_password; print(hash_password('...'))"`).

## Déploiement

Le workflow `.github/workflows/ci-cd.yml` build l'image, la pousse sur
`ghcr.io/enervision-g4/enervision-api`, puis appelle le workflow réutilisable
de `enervision-devops` (`deploy.yml`) qui déploie sur le serveur on-premise
via `compose/api.yml`. Voir le README de `enervision-devops` pour le détail
du mécanisme et les secrets GitHub à configurer (environnement `onprem`).
