"""Add unique constraint on notification_logs (recipient_user_id, advisory_id, channel)

Revision ID: 0005
Revises: 0004
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_notification_recipient_advisory_channel",
        "notification_logs",
        ["recipient_user_id", "advisory_id", "channel"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_notification_recipient_advisory_channel",
        "notification_logs",
        type_="unique",
    )
