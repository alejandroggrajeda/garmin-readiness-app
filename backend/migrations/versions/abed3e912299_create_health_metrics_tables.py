"""create health metrics tables (raw_payloads, daily_metrics)

Revision ID: abed3e912299
Revises:
Create Date: 2026-08-02

Creates the two Phase 3 (health-metrics-store) tables per design.md's
"Data Model": `raw_payloads` (append-only raw Garmin responses) and
`daily_metrics` (upserted, normalized per-day cache). Types match
`app/store/models.py` exactly. `daily_metrics.source_run_id` is a plain
UUID column with no FK yet — `sync_runs` (Phase 5) doesn't exist until the
next migration.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "abed3e912299"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "raw_payloads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("metric_date", sa.Date(), nullable=False),
        sa.Column("endpoint", sa.String(length=32), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_raw_payloads")),
    )
    op.create_index(
        op.f("ix_raw_payloads_metric_date"),
        "raw_payloads",
        ["metric_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_raw_payloads_endpoint"), "raw_payloads", ["endpoint"], unique=False
    )

    op.create_table(
        "daily_metrics",
        sa.Column("metric_date", sa.Date(), nullable=False),
        sa.Column("hrv_last_night", sa.Integer(), nullable=True),
        sa.Column("hrv_status", sa.String(length=32), nullable=True),
        sa.Column("body_battery_max", sa.Integer(), nullable=True),
        sa.Column("body_battery_min", sa.Integer(), nullable=True),
        sa.Column("sleep_score", sa.Integer(), nullable=True),
        sa.Column("sleep_duration_s", sa.Integer(), nullable=True),
        sa.Column("stress_avg", sa.Integer(), nullable=True),
        sa.Column("resting_hr", sa.Integer(), nullable=True),
        sa.Column("recovery_time_h", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("acute_load", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("chronic_load", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("source_run_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("metric_date", name=op.f("pk_daily_metrics")),
    )


def downgrade() -> None:
    op.drop_table("daily_metrics")
    op.drop_index(op.f("ix_raw_payloads_endpoint"), table_name="raw_payloads")
    op.drop_index(op.f("ix_raw_payloads_metric_date"), table_name="raw_payloads")
    op.drop_table("raw_payloads")
