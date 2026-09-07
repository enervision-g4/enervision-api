from datetime import datetime, timezone

from fastapi import FastAPI

from app.routers import alerts, auth, predictions, readings, recommendations, sites

app = FastAPI(
    title="EnerVision API",
    description="API sécurisée exposant les données de consommation énergétique "
    "(sites, mesures, alertes, prédictions, recommandations) au dashboard.",
    version="0.1.0",
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
