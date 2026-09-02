# enervision-api

API sécurisée (FastAPI) exposant au dashboard les données de consommation
énergétique stockées dans TimescaleDB (voir `enervision-devops`) : sites,
mesures, alertes. Authentification par JWT (`POST /auth/login`).

## Lancer en local

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # renseigner DATABASE_URL vers une instance TimescaleDB
uvicorn app.main:app --reload --port 3000
```

Documentation interactive : http://localhost:3000/docs

## Structure

```
app/
├── main.py          # point d'entrée FastAPI, montage des routers
├── config.py         # settings (pydantic-settings) depuis l'environnement
├── database.py       # engine SQLAlchemy + dépendance get_db
├── models.py          # modèles ORM (miroir des tables créées par
│                        enervision-devops/db/init/002_create_tables.sql)
├── schemas.py         # schémas Pydantic (réponses API)
├── security.py        # JWT (création/validation de token)
└── routers/
    ├── auth.py         # POST /auth/login
    ├── sites.py         # GET /api/v1/sites, GET /api/v1/sites/{site_id}
    ├── readings.py       # GET /api/v1/readings
    └── alerts.py         # GET /api/v1/alerts
```

## Déploiement

Le workflow `.github/workflows/ci-cd.yml` build l'image, la pousse sur
`ghcr.io/enervision-g4/enervision-api`, puis appelle le workflow réutilisable
de `enervision-devops` (`deploy.yml`) qui déploie sur le serveur on-premise
via `compose/api.yml`. Voir le README de `enervision-devops` pour le détail
du mécanisme et les secrets GitHub à configurer (environnement `onprem`).
