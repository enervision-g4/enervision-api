"""Modèles SQLAlchemy — miroir des tables créées par
enervision-devops/db/init/002_create_tables.sql (issues du MCD,
Ressources/mcd-projet-piscine.png).

Ces modèles ne créent rien (pas de Base.metadata.create_all) : les tables
sont la propriété du script d'init côté devops. L'API se contente de lire
dans un schéma qui existe déjà.
"""

import uuid

from sqlalchemy import (
    ARRAY,
    TIMESTAMP,
    Double,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


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
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    timestamp: Mapped[object] = mapped_column(
        "timestamp", TIMESTAMP(timezone=True), primary_key=True
    )
    site_id: Mapped[str] = mapped_column(String, ForeignKey("site.site_id"), nullable=False)
    consumption_kw: Mapped[float | None] = mapped_column(Double)
    consumption_kwh: Mapped[float | None] = mapped_column(Double)
    voltage_v: Mapped[float | None] = mapped_column(Double)
    current_a: Mapped[float | None] = mapped_column(Double)
    power_factor: Mapped[float | None] = mapped_column(Double)
    temperature_celsius: Mapped[float | None] = mapped_column(Double)
    humidity_percent: Mapped[float | None] = mapped_column(Double)
    null_reasons: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    data_quality: Mapped[str | None] = mapped_column(String)


class Alert(Base):
    __tablename__ = "alert"
    __table_args__ = (
        UniqueConstraint(
            "source_alert_id", "timestamp", name="uq_alert_source_alert_id"
        ),
    )

    alert_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Identifiant attribué par l'API source (ex. ALR-SITE002-1718458320). Plus parlant
    # qu'un UUID pour qui lit une alerte, et clé d'idempotence côté ingestion.
    source_alert_id: Mapped[str] = mapped_column(String, nullable=False)
    timestamp: Mapped[object] = mapped_column(
        "timestamp", TIMESTAMP(timezone=True), primary_key=True
    )
    site_id: Mapped[str] = mapped_column(String, ForeignKey("site.site_id"), nullable=False)
    severity: Mapped[str | None] = mapped_column(String)
    type: Mapped[str | None] = mapped_column(String)
    message: Mapped[str | None] = mapped_column(String)
    value_kw: Mapped[float | None] = mapped_column(Double)
    threshold_kw: Mapped[float | None] = mapped_column(Double)
