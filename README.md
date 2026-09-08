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
| `GET /api/v1/alerts` | Alertes paginées (`page`, `limit`), triables (`sort_by`: `timestamp`/`severity`/`site_id`, `order`: `asc`/`desc`), filtrables (`site_id`, `severity`, `start_time`, `end_time`) — réponse `{items, total, page, limit}` |
| `GET /api/v1/alerts/summary` | Nombre d'alertes par sévérité (`site_id`, `start_time`, `end_time`) |
| `GET /api/v1/predictions` | Prédictions de consommation (`site_id`, `model_version`, `limit`), triées par horizon (`target_timestamp`) croissant |
| `GET /api/v1/recommendations` | Recommandations d'actions correctives (`site_id`, `status`, `limit`), les plus récentes d'abord |

## Temps réel (WebSocket)

`GET /ws/readings?site_id=...&token=...[&since=...]` et
`GET /ws/alerts?token=...[&site_id=...][&since=...]` poussent respectivement chaque nouvelle
mesure/alerte dès qu'elle apparaît en base (poll interne toutes les 5s, ne pousse que les lignes
nouvelles). Le token JWT est passé en query string — un WebSocket natif ne peut pas poser de header
`Authorization` depuis un navigateur — jamais dans l'URL en clair côté logs serveur puisqu'il expire vite
(`JWT_EXPIRE_MINUTES`), mais à garder en tête si des access logs bruts sont un jour activés. Ce n'est pas
un vrai push événementiel (l'ETL/les consumers Kafka écrivent en base sans notifier l'API) : c'est un
polling côté serveur toutes les 5s, mais le client ne voit que des messages utiles (aucun trafic quand
rien de neuf), contrairement au polling HTTP précédent qui redemandait tout à chaque fois.

Points de contrat à connaître côté client :

- **`since`** (ISO 8601, optionnel) : horodatage de la donnée la plus récente que le client a déjà
  chargée en REST. Le flux reprend strictement après cette date — ni trou, ni rejeu. **Sans `since`, le
  flux démarre au dernier horodatage présent en base : l'historique n'est jamais rejoué.** À encoder
  (le `+00:00` d'un fuseau devient une espace s'il n'est pas échappé) ; `URLSearchParams` le fait.
- **`{"type": "heartbeat"}`** : trame envoyée toutes les ~25s de silence pour que les reverse-proxy ne
  coupent pas une connexion inactive. À ignorer côté client.
- **Fin de connexion** : le serveur attend en parallèle un message du client, ce qui lui fait détecter
  immédiatement une déconnexion. Sans cette attente, un client parti n'était repéré qu'au premier envoi
  en échec — donc jamais tant qu'aucune donnée neuve n'arrivait, et chaque navigation dans le dashboard
  laissait derrière elle une boucle qui continuait d'interroger la base (cause du conteneur d'API à
  +50% de CPU). Couvert par `tests/test_live.py::test_ws_stops_polling_when_client_disconnects`.
- **Plafond** : 200 connexions simultanées (`MAX_CONCURRENT_CONNECTIONS`), au-delà la connexion est
  refusée avec le code 1013 ("try again later").

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
    ├── recommendations.py  # GET /api/v1/recommendations
    └── live.py             # GET /ws/readings, GET /ws/alerts (WebSocket)
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

`CORS_ALLOWED_ORIGINS` (une ou plusieurs origines séparées par des virgules)
doit être l'URL exacte (protocole+hôte+port) depuis laquelle le dashboard est
servi, sinon le navigateur bloque tous ses appels à l'API (CORS). En
déploiement, doit correspondre à `API_URL`/`DASHBOARD_PORT` du même
environnement — voir `enervision-devops/envs/onprem.env.example`.

## Déploiement

Le workflow `.github/workflows/ci-cd.yml` build l'image, la pousse sur
`ghcr.io/enervision-g4/enervision-api`, puis appelle le workflow réutilisable
de `enervision-devops` (`deploy.yml`) qui déploie sur le serveur on-premise
via `compose/api.yml`. Voir le README de `enervision-devops` pour le détail
du mécanisme et les secrets GitHub à configurer (environnement `onprem`).
