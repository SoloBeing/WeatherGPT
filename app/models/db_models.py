"""
SQLAlchemy ORM Models — PostGIS + TimescaleDB tables.

Tables:
  - forecast_cycles:   registered GFS/ECMWF runs (model, run_time, valid_range, zarr_path)
  - alerts:            CAP alerts with PostGIS geometry column (ST_Intersects ready)
  - user_locations:    user subscriptions with PostGIS point (for spatial alert fan-out)
  - gazetteer:         Indian place names (LGD/GeoNames) with coordinates and spatial point
  - observations:      station timeseries (TimescaleDB hypertable target)
"""

from datetime import datetime
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class ForecastCycle(Base):
    """
    Metadata for ingested numerical weather prediction cycles (GFS / ECMWF).
    Tracks when cycles land, validity horizon, and corresponding Zarr store paths.
    """
    __tablename__ = "forecast_cycles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    model: Mapped[str] = mapped_column(String(64), index=True)  # e.g. "GFS_0.25", "ECMWF_IFS"
    cycle_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)  # cycle run e.g. 2026-09-04 12:00:00Z
    cycle_hour: Mapped[int] = mapped_column(Integer)  # 0, 6, 12, 18
    valid_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    horizon_hours: Mapped[int] = mapped_column(Integer, default=384)
    zarr_path: Mapped[str] = mapped_column(String(512))  # s3://... or file://...
    variables: Mapped[list[str]] = mapped_column(JSON, default=list)  # ["t2m", "u10", "v10", "tp", "sp"]
    bbox: Mapped[dict[str, float] | None] = mapped_column(JSON, nullable=True)  # {"min_lat": 6.0, ...}
    status: Mapped[str] = mapped_column(String(32), default="READY", index=True)  # READY, INGESTING, FAILED
    records_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_forecast_cycles_model_cycle", "model", "cycle_time", unique=True),
    )


class Alert(Base):
    """
    CAP alerts from NDMA SACHET and IMD with PostGIS geometry for spatial polygon indexing.
    Used for instant spatial intersection (ST_Intersects) against user coordinates.
    """
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    identifier: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    sender: Mapped[str | None] = mapped_column(String(256), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="Actual")
    msg_type: Mapped[str] = mapped_column(String(32), default="Alert")
    source: Mapped[str] = mapped_column(String(64), default="SACHET", index=True)
    scope: Mapped[str] = mapped_column(String(32), default="Public")
    category: Mapped[str] = mapped_column(String(64), default="Met")
    event: Mapped[str] = mapped_column(String(256), index=True)
    urgency: Mapped[str] = mapped_column(String(32), default="Unknown")
    severity: Mapped[str] = mapped_column(String(32), default="Unknown", index=True)
    certainty: Mapped[str] = mapped_column(String(32), default="Unknown")
    headline: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    instruction: Mapped[str | None] = mapped_column(Text, nullable=True)
    effective: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    onset: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    area_desc: Mapped[str | None] = mapped_column(Text, nullable=True)
    polygon_geojson: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSON, nullable=True)
    geom: Mapped[Any] = mapped_column(
        Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_alerts_active_filter", "status", "expires", "severity"),
    )


class UserLocation(Base):
    """
    User subscriptions and registered locations with PostGIS Point geometry.
    Enables proactive push notification fan-out when severe weather polygons intersect.
    """
    __tablename__ = "user_locations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    fcm_token: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    label: Mapped[str | None] = mapped_column(String(128), nullable=True)  # e.g. "Home", "Farm"
    state: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    district: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    geom: Mapped[Any] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=True),
        nullable=True,
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_user_locations_active_district", "active", "state", "district"),
    )


class Gazetteer(Base):
    """
    Gazetteer for Indian place names (States, Districts, Towns, Villages).
    Pre-resolves ambiguous spoken/typed location names before the LLM sees the prompt.
    """
    __tablename__ = "gazetteer"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), index=True)
    name_hi: Mapped[str | None] = mapped_column(String(256), nullable=True)
    state: Mapped[str] = mapped_column(String(128), index=True)
    district: Mapped[str] = mapped_column(String(128), index=True)
    subdistrict: Mapped[str | None] = mapped_column(String(128), nullable=True)
    category: Mapped[str] = mapped_column(String(64), default="town", index=True)
    pincode: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    geom: Mapped[Any] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=True),
        nullable=True,
    )
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index(
            "ix_gazetteer_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
        Index(
            "ix_gazetteer_name_hi_trgm",
            "name_hi",
            postgresql_using="gin",
            postgresql_ops={"name_hi": "gin_trgm_ops"},
        ),
    )


class Observation(Base):
    """
    Station weather timeseries (TimescaleDB hypertable target).
    Captures ground truth observations from IMD AWS, MOSDAC, and Synoptic stations.
    """
    __tablename__ = "observations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    station_id: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[str] = mapped_column(String(64), default="IMD_AWS", index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    relative_humidity: Mapped[float | None] = mapped_column(Float, nullable=True)
    pressure_hpa: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_speed_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_direction_deg: Mapped[float | None] = mapped_column(Float, nullable=True)
    precipitation_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    condition: Mapped[str | None] = mapped_column(String(128), nullable=True)
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_obs_station_time", "station_id", "recorded_at"),
    )

