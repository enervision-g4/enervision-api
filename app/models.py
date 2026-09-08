"""Modèles SQLAlchemy — miroir des tables créées par
enervision-devops/db/init/002_create_tables.sql (issues du MCD,
Ressources/mcd-projet-piscine.png).

Ces modèles ne créent rien en production (pas de Base.metadata.create_all
hors tests) : les tables sont la propriété du script d'init côté devops.
L'API se contente de lire dans un schéma qui existe déjà.

Types choisis volontairement cross-dialecte (`Uuid`, `ARRAY(...).with_variant`)
plutôt que `sqlalchemy.dialects.postgresql.*` : les tests unitaires tournent
sur SQLite en mémoire (voir tests/conftest.py) sans base externe à
provisionner, tout en gardant un stockage natif (UUID/ARRAY réels) une fois
déployé sur la vraie base Postgres/TimescaleDB.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    ARRAY,
    JSON,
    TIMESTAMP,
    Double,
    ForeignKey,
    Integer,
    String,
    TypeDecorator,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# ARRAY(String) natif sur Postgres ; sur SQLite (tests), pas de type ARRAY —
# stocké en JSON, qui (dé)sérialise vers/depuis list[str] de façon transparente
# côté Python : le comportement observé par les modèles/schémas est identique.
_STRING_ARRAY = ARRAY(String).with_variant(JSON(), "sqlite")


class _UtcTimestamp(TypeDecorator):
    """TIMESTAMP(timezone=True), mais qui garantit un datetime *aware* (UTC)
    à la lecture, y compris sur SQLite.

    Postgres renvoie déjà des datetimes aware pour une colonne
    `timezone=True` ; SQLite, lui, ne stocke aucune information de fuseau et
    rend systématiquement un datetime naïf. Sans ce correctif, le même code
    applicatif (comparaisons, sérialisation JSON avec suffixe "Z"...) se
    comporterait différemment en test (SQLite) et en production (Postgres) —
    exactement le genre d'écart qu'une suite de tests est censée exclure.
    """

    impl = TIMESTAMP(timezone=True)
    cache_ok = True

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value


class Site(Base):
    __tablename__ = "site"

    site_id: Mapped[str] = mapped_column(String, primary_key=True)
    site_type: Mapped[str] = mapped_column(String, nullable=False)
    site_name: Mapped[str] = mapped_column(String, nullable=False)
    location: Mapped[str | None] = mapped_column(String)
    capacity_kw: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str | None] = mapped_column(String)


class MeasureRaw(Base):
    __tablename__ = "measure_raw"
    # Clé métier de la mesure, sur laquelle le consumer s'appuie pour une insertion
    # idempotente. Déclarée ici pour que le schéma créé en test reste fidèle à celui
    # du script d'init, seul propriétaire des tables en production.
    __table_args__ = (
        UniqueConstraint("site_id", "timestamp", name="uq_measure_raw_site_timestamp"),
    )

    measure_raw_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    timestamp: Mapped[object] = mapped_column("timestamp", _UtcTimestamp(), primary_key=True)
    site_id: Mapped[str] = mapped_column(String, ForeignKey("site.site_id"), nullable=False)
    consumption_kw: Mapped[float | None] = mapped_column(Double)
    consumption_kwh: Mapped[float | None] = mapped_column(Double)
    voltage_v: Mapped[float | None] = mapped_column(Double)
    current_a: Mapped[float | None] = mapped_column(Double)
    power_factor: Mapped[float | None] = mapped_column(Double)
    temperature_celsius: Mapped[float | None] = mapped_column(Double)
    humidity_percent: Mapped[float | None] = mapped_column(Double)
    null_reasons: Mapped[list[str] | None] = mapped_column(_STRING_ARRAY)
    data_quality: Mapped[str | None] = mapped_column(String)


class Alert(Base):
    __tablename__ = "alert"
    __table_args__ = (
        UniqueConstraint("source_alert_id", "timestamp", name="uq_alert_source_alert_id"),
    )

    alert_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Identifiant attribué par l'API source (ex. ALR-SITE002-1718458320). Plus parlant
    # qu'un UUID pour qui lit une alerte, et clé d'idempotence côté ingestion.
    source_alert_id: Mapped[str] = mapped_column(String, nullable=False)
    timestamp: Mapped[object] = mapped_column("timestamp", _UtcTimestamp(), primary_key=True)
    site_id: Mapped[str] = mapped_column(String, ForeignKey("site.site_id"), nullable=False)
    severity: Mapped[str | None] = mapped_column(String)
    type: Mapped[str | None] = mapped_column(String)
    message: Mapped[str | None] = mapped_column(String)
    value_kw: Mapped[float | None] = mapped_column(Double)
    threshold_kw: Mapped[float | None] = mapped_column(Double)


class Prediction(Base):
    __tablename__ = "prediction"

    prediction_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    site_id: Mapped[str] = mapped_column(String, ForeignKey("site.site_id"), nullable=False)
    target_timestamp: Mapped[object | None] = mapped_column(_UtcTimestamp())
    predicted_consumption_kw: Mapped[float | None] = mapped_column(Double)
    threshold_kw: Mapped[float | None] = mapped_column(Double)
    model_version: Mapped[str | None] = mapped_column(String)
    # Horodatage de génération de la prédiction (colonne de partitionnement de
    # l'hypertable), distinct de target_timestamp qui est l'horizon prédit.
    timestamp: Mapped[object] = mapped_column("timestamp", _UtcTimestamp(), primary_key=True)


class Recommendation(Base):
    __tablename__ = "recommendation"

    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    site_id: Mapped[str] = mapped_column(String, ForeignKey("site.site_id"), nullable=False)
    # Pas de ForeignKey : une hypertable ne peut pas porter la contrainte UNIQUE sur
    # (prediction_id) seul qu'exigerait une FK vers "prediction" (voir le commentaire
    # en tête de 002_create_tables.sql). Lien simplement indexé côté devops.
    prediction_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    timestamp: Mapped[object] = mapped_column("timestamp", _UtcTimestamp(), primary_key=True)
    action_description: Mapped[str | None] = mapped_column(String)
    status: Mapped[str | None] = mapped_column(String)
