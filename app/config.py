from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration chargée depuis l'environnement (.env en local,
    variables injectées par compose/api.yml en déploiement)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    api_username: str
    api_password_hash: str

    # Liste d'origines autorisées en CORS, séparées par des virgules — l'API et le
    # dashboard sont sur des ports différents (jamais la même origine), le navigateur
    # bloque donc les appels du dashboard sans ça. Défaut : serveur de dev Vite local.
    cors_allowed_origins: str = "http://localhost:5173"

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]


settings = Settings()
