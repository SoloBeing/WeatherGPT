"""Performance and spatial indexes: GIN trigram and composite filter indexes

Revision ID: 0002_performance_and_spatial_indexes
Revises: 0001_initial_schema
Create Date: 2026-09-06 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_performance_and_spatial_indexes"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Trigram GIN indexes on gazetteer for sub-millisecond fuzzy location matching
    op.create_index(
        "ix_gazetteer_name_trgm",
        "gazetteer",
        ["name"],
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_gazetteer_name_hi_trgm",
        "gazetteer",
        ["name_hi"],
        postgresql_using="gin",
        postgresql_ops={"name_hi": "gin_trgm_ops"},
    )

    # 2. Composite query indexes for active alert filtering and user location fan-out
    op.create_index(
        "ix_alerts_active_filter",
        "alerts",
        ["status", "expires", "severity"],
    )
    op.create_index(
        "ix_user_locations_active_district",
        "user_locations",
        ["active", "state", "district"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_locations_active_district", table_name="user_locations")
    op.drop_index("ix_alerts_active_filter", table_name="alerts")
    op.drop_index("ix_gazetteer_name_hi_trgm", table_name="gazetteer")
    op.drop_index("ix_gazetteer_name_trgm", table_name="gazetteer")
