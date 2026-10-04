"""Align rules, irrigation sources, consent, and forecast columns to spec

Revision ID: 0006
Revises: 0005
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add new irrigation enum values to Postgres
    # PostgreSQL supports ALTER TYPE ... ADD VALUE IF NOT EXISTS
    op.execute("ALTER TYPE irrigationsource ADD VALUE IF NOT EXISTS 'BOREWELL_WELL';")
    op.execute("ALTER TYPE irrigationsource ADD VALUE IF NOT EXISTS 'TANK_POND';")
    op.execute("ALTER TYPE irrigationsource ADD VALUE IF NOT EXISTS 'DRIP_SPRINKLER';")

    # 2. Add LOW and MEDIUM to advisoryseverity enum
    op.execute("ALTER TYPE advisoryseverity ADD VALUE IF NOT EXISTS 'LOW';")
    op.execute("ALTER TYPE advisoryseverity ADD VALUE IF NOT EXISTS 'MEDIUM';")

    # 3. Add BLOCKED_CONSENT and BLOCKED_OPT_OUT and BLOCKED_NON_LIVE to notificationstatus
    op.execute("ALTER TYPE notificationstatus ADD VALUE IF NOT EXISTS 'BLOCKED_CONSENT';")
    op.execute("ALTER TYPE notificationstatus ADD VALUE IF NOT EXISTS 'BLOCKED_OPT_OUT';")
    op.execute("ALTER TYPE notificationstatus ADD VALUE IF NOT EXISTS 'BLOCKED_NON_LIVE';")

    # 4. Add channel-specific consent and opt-out columns to users
    op.add_column("users", sa.Column("whatsapp_consent", sa.Boolean(), server_default="true", nullable=False))
    op.add_column("users", sa.Column("sms_consent", sa.Boolean(), server_default="true", nullable=False))
    op.add_column("users", sa.Column("opted_out_at", sa.DateTime(timezone=True), nullable=True))

    # 5. Add false_onset_prob and break_duration_days_p50 to grid_forecasts
    op.add_column("grid_forecasts", sa.Column("false_onset_prob", sa.Float(), server_default="0.20", nullable=True))
    op.add_column("grid_forecasts", sa.Column("break_duration_days_p50", sa.Float(), server_default="7.0", nullable=True))


def downgrade() -> None:
    op.drop_column("grid_forecasts", "break_duration_days_p50")
    op.drop_column("grid_forecasts", "false_onset_prob")
    op.drop_column("users", "opted_out_at")
    op.drop_column("users", "sms_consent")
    op.drop_column("users", "whatsapp_consent")
