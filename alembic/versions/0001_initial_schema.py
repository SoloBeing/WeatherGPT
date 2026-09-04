"""Initial schema: PostGIS + TimescaleDB tables

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-09-04 22:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geometry

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Enable PostgreSQL Extensions (PostGIS, pg_trgm, TimescaleDB)
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
    op.execute("""
    DO $$
    BEGIN
        CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE 'TimescaleDB extension not available or permission denied, skipping.';
    END $$;
    """)

    # 2. Table: forecast_cycles
    op.create_table(
        "forecast_cycles",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("cycle_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cycle_hour", sa.Integer(), nullable=False),
        sa.Column("valid_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("horizon_hours", sa.Integer(), nullable=False, server_default="384"),
        sa.Column("zarr_path", sa.String(length=512), nullable=False),
        sa.Column("variables", sa.JSON(), nullable=False),
        sa.Column("bbox", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="READY"),
        sa.Column("records_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_forecast_cycles_model", "forecast_cycles", ["model"])
    op.create_index("ix_forecast_cycles_cycle_time", "forecast_cycles", ["cycle_time"])
    op.create_index("ix_forecast_cycles_status", "forecast_cycles", ["status"])
    op.create_index("ix_forecast_cycles_model_cycle", "forecast_cycles", ["model", "cycle_time"], unique=True)

    # 3. Table: alerts (NDMA SACHET + IMD CAP alerts with PostGIS geometry)
    op.create_table(
        "alerts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("identifier", sa.String(length=256), nullable=False),
        sa.Column("sender", sa.String(length=256), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="Actual"),
        sa.Column("msg_type", sa.String(length=32), nullable=False, server_default="Alert"),
        sa.Column("source", sa.String(length=64), nullable=False, server_default="SACHET"),
        sa.Column("scope", sa.String(length=32), nullable=False, server_default="Public"),
        sa.Column("category", sa.String(length=64), nullable=False, server_default="Met"),
        sa.Column("event", sa.String(length=256), nullable=False),
        sa.Column("urgency", sa.String(length=32), nullable=False, server_default="Unknown"),
        sa.Column("severity", sa.String(length=32), nullable=False, server_default="Unknown"),
        sa.Column("certainty", sa.String(length=32), nullable=False, server_default="Unknown"),
        sa.Column("headline", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("instruction", sa.Text(), nullable=True),
        sa.Column("effective", sa.DateTime(timezone=True), nullable=True),
        sa.Column("onset", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires", sa.DateTime(timezone=True), nullable=True),
        sa.Column("area_desc", sa.Text(), nullable=True),
        sa.Column("polygon_geojson", sa.JSON(), nullable=True),
        sa.Column("geom", Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alerts_identifier", "alerts", ["identifier"], unique=True)
    op.create_index("ix_alerts_source", "alerts", ["source"])
    op.create_index("ix_alerts_event", "alerts", ["event"])
    op.create_index("ix_alerts_severity", "alerts", ["severity"])
    op.create_index("ix_alerts_expires", "alerts", ["expires"])

    # 4. Table: user_locations (User subscriptions for spatial alert matching)
    op.create_table(
        "user_locations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("fcm_token", sa.String(length=512), nullable=True),
        sa.Column("label", sa.String(length=128), nullable=True),
        sa.Column("state", sa.String(length=128), nullable=True),
        sa.Column("district", sa.String(length=128), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("geom", Geometry(geometry_type="POINT", srid=4326, spatial_index=True), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_locations_user_id", "user_locations", ["user_id"])
    op.create_index("ix_user_locations_fcm_token", "user_locations", ["fcm_token"])
    op.create_index("ix_user_locations_state", "user_locations", ["state"])
    op.create_index("ix_user_locations_district", "user_locations", ["district"])
    op.create_index("ix_user_locations_active", "user_locations", ["active"])

    # 5. Table: gazetteer (Indian place names with coordinates and spatial point)
    op.create_table(
        "gazetteer",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("name_hi", sa.String(length=256), nullable=True),
        sa.Column("state", sa.String(length=128), nullable=False),
        sa.Column("district", sa.String(length=128), nullable=False),
        sa.Column("subdistrict", sa.String(length=128), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=False, server_default="town"),
        sa.Column("pincode", sa.String(length=16), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("geom", Geometry(geometry_type="POINT", srid=4326, spatial_index=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_gazetteer_name", "gazetteer", ["name"])
    op.create_index("ix_gazetteer_state", "gazetteer", ["state"])
    op.create_index("ix_gazetteer_district", "gazetteer", ["district"])
    op.create_index("ix_gazetteer_category", "gazetteer", ["category"])
    op.create_index("ix_gazetteer_pincode", "gazetteer", ["pincode"])

    # 6. Table: observations (Station timeseries hypertable)
    op.create_table(
        "observations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("station_id", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False, server_default="IMD_AWS"),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("temperature_c", sa.Float(), nullable=True),
        sa.Column("relative_humidity", sa.Float(), nullable=True),
        sa.Column("pressure_hpa", sa.Float(), nullable=True),
        sa.Column("wind_speed_ms", sa.Float(), nullable=True),
        sa.Column("wind_direction_deg", sa.Float(), nullable=True),
        sa.Column("precipitation_mm", sa.Float(), nullable=True),
        sa.Column("condition", sa.String(length=128), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_observations_station_id", "observations", ["station_id"])
    op.create_index("ix_observations_source", "observations", ["source"])
    op.create_index("ix_observations_recorded_at", "observations", ["recorded_at"])
    op.create_index("ix_obs_station_time", "observations", ["station_id", "recorded_at"])

    # 7. Convert observations to TimescaleDB hypertable if timescaledb is loaded
    op.execute("""
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
            PERFORM create_hypertable('observations', 'recorded_at', if_not_exists => TRUE);
        END IF;
    END $$;
    """)


def downgrade() -> None:
    op.drop_table("observations")
    op.drop_table("gazetteer")
    op.drop_table("user_locations")
    op.drop_table("alerts")
    op.drop_table("forecast_cycles")
