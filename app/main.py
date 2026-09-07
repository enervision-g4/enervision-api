from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import alerts, auth, predictions, readings, recommendations, sites

app = FastAPI(
    title="EnerVision API",
    description="API sécurisée exposant les données de consommation énergétique "
    "(sites, mesures, alertes, prédictions, recommandations) au dashboard.",
    version="0.1.0",
)

# Le dashboard (SPA statique) et l'API tournent toujours sur des ports différents,
# donc jamais la même origine pour le navigateur : sans CORS explicite, chaque appel
# XHR du dashboard (à commencer par /auth/login) est bloqué côté navigateur avant
# même d'atteindre l'API. allow_credentials=False : l'auth passe par un header
# Authorization Bearer (JWT en localStorage côté dashboard), jamais par un cookie —
# CORS n'a donc pas besoin d'autoriser les credentials.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins_list,
    allow_credentials=False,
    # Liste explicite plutôt que "*" : documente ce dont l'API a réellement besoin
    # (principe de moindre privilège). Ne change rien à la sécurité réelle — CORS
    # protège le navigateur du client, pas le serveur, qui reste protégé par le JWT
    # (Depends(get_current_subject)) sur chaque route indépendamment de ces headers.
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth.router)
app.include_router(sites.router)
app.include_router(readings.router)
app.include_router(alerts.router)
app.include_router(predictions.router)
app.include_router(recommendations.router)


@app.get("/health", tags=["health"])
def health():
    """Utilisé par Docker/le healthcheck de compose/api.yml."""
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}
