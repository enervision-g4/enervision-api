# Configuration

Comme `enervision-etl` et `enervision-ml`, toute la configuration passe par des
variables d'environnement (`pydantic_settings.BaseSettings`, `app/config.py`) — jamais
d'adresse ou de secret codé en dur. Un champ sans valeur par défaut dans le code est
**obligatoire** : son absence fait échouer le démarrage immédiatement, avec un message
explicite.

```bash
cp .env.example .env   # puis éditer .env
```

## Variables

| Variable | Rôle | Défaut |
|---|---|---|
| `DATABASE_URL` | Connexion à TimescaleDB (schéma `postgresql+psycopg://`). **Obligatoire.** | — |
| `JWT_SECRET_KEY` | Clé de signature des jetons JWT. **Obligatoire.** | — |
| `JWT_ALGORITHM` | Algorithme de signature. | `HS256` |
| `JWT_EXPIRE_MINUTES` | Durée de validité d'un jeton. | `60` |
| `API_USERNAME` | Identifiant du compte de service. **Obligatoire.** | — |
| `API_PASSWORD_HASH` | Hash Argon2id du mot de passe (jamais le mot de passe en clair). **Obligatoire.** | — |
| `CORS_ALLOWED_ORIGINS` | Origine(s) autorisées pour le dashboard, séparées par des virgules. | `http://localhost:5173` |

## Pourquoi `postgresql+psycopg://` et pas `postgres://`

`DATABASE_URL` doit commencer par `postgresql+psycopg://` : c'est le schéma que
SQLAlchemy attend pour sélectionner le driver `psycopg` (v3), utilisé par ce projet en
variante binaire (`psycopg[binary]`, qui embarque déjà `libpq` — l'image finale reste
sans chaîne de compilation, voir
[08-deploiement-et-flux-devops.md](08-deploiement-et-flux-devops.md)). C'est une
différence à connaître face à `enervision-ml`, qui utilise `psycopg` directement (sans
SQLAlchemy) et attend un schéma nu `postgresql://` — un suffixe de pilote SQLAlchemy y
serait au contraire retiré. `DATABASE_URL` est partagée entre plusieurs services du
parc EnerVision qui n'utilisent pas tous la même bibliothèque d'accès à la base ; chaque
service adapte le schéma à ce dont **lui** a besoin.

## `database.py` : une session par requête

```python
engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

`get_db` est une dépendance FastAPI (`Depends(get_db)`) : une nouvelle session
SQLAlchemy est ouverte pour chaque requête, et systématiquement fermée à la fin (le
`finally` s'exécute même en cas d'exception dans la route) — pas de connexion partagée
entre requêtes concurrentes, pas de fuite de connexion. `pool_pre_ping=True` teste
chaque connexion avant de la réutiliser depuis le pool, pour détecter une connexion
tombée (base redémarrée, coupure réseau) plutôt que d'échouer sur la première requête qui
l'utiliserait.

## Suite

- [08-deploiement-et-flux-devops.md](08-deploiement-et-flux-devops.md) — comment ces
  variables sont injectées en production, et le flux de déploiement complet.
