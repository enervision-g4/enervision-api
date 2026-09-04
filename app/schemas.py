import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SiteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    site_id: str
    site_type: str
    site_name: str
    location: str | None = None
    capacity_kw: int | None = None
    status: str | None = None


class ReadingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    timestamp: datetime
    site_id: str
    consumption_kw: float | None = None
    consumption_kwh: float | None = None
    voltage_v: float | None = None
    current_a: float | None = None
    power_factor: float | None = None
    temperature_celsius: float | None = None
    humidity_percent: float | None = None
    null_reasons: list[str] | None = None
    data_quality: str | None = None


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    # Typé en UUID et non en str : pydantic ne convertit pas l'un en l'autre et
    # refusait la réponse. FastAPI le rend en chaîne dans le JSON.
    alert_id: uuid.UUID
    source_alert_id: str
    timestamp: datetime
    site_id: str
    severity: str | None = None
    type: str | None = None
    message: str | None = None
    value_kw: float | None = None
    threshold_kw: float | None = None


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
