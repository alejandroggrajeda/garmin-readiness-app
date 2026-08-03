"""create sync_runs, garmin_session tables; add daily_metrics FK

Revision ID: c7a1f5e3b9d2
Revises: abed3e912299
Create Date: 2026-08-02

Phase 5 (garmin-sync, readiness-api "Manual Sync" scope). Creates the two
tables `app/sync/*` and `routes/sync.py` depend on, then adds the FK from
`daily_metrics.source_run_id` -> `sync_runs.id` deferred from the Phase 3
migration (`abed3e912299`) because `sync_runs` did not exist yet.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c7a1f5e3b9d2"
down_revision: Union[str, None] = "abed3e912299"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sync_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="running"
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "heartbeat_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.String(length=1024), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sync_runs")),
    )

    op.create_table(
        "garmin_session",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token_cache_enc", sa.LargeBinary(), nullable=True),
        sa.Column(
            "auth_locked", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_garmin_session")),
    )

    op.create_foreign_key(
        op.f("fk_daily_metrics_source_run_id_sync_runs"),
        "daily_metrics",
        "sync_runs",
        ["source_run_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_daily_metrics_source_run_id_sync_runs"),
        "daily_metrics",
        type_="foreignkey",
    )
    op.drop_table("garmin_session")
    op.drop_table("sync_runs")
