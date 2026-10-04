"""Phase 3: Add is_trained to model_versions, issue_date/source_url columns to global_indices

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add is_trained to model_versions
    op.add_column(
        "model_versions",
        sa.Column("is_trained", sa.Boolean(), nullable=False, server_default="false"),
    )

    # Rename global_indices.date → issue_date (allow multiple per date now)
    # First add new column, copy data, drop old
    op.add_column(
        "global_indices",
        sa.Column("issue_date", sa.Date(), nullable=True),
    )
    op.execute("UPDATE global_indices SET issue_date = date WHERE issue_date IS NULL")
    op.alter_column("global_indices", "issue_date", nullable=False)

    # Add source_url columns
    op.add_column("global_indices", sa.Column("source_url_oni", sa.String(255), nullable=True))
    op.add_column("global_indices", sa.Column("source_url_mjo", sa.String(255), nullable=True))
    op.add_column("global_indices", sa.Column("source_url_dmi", sa.String(255), nullable=True))

    # Drop the old unique constraint on date column
    op.drop_index("ix_global_indices_date", table_name="global_indices")
    op.create_index("ix_global_indices_issue_date", "global_indices", ["issue_date"])

    # Drop the old date column (data is now in issue_date)
    op.drop_column("global_indices", "date")


def downgrade() -> None:
    op.add_column(
        "global_indices",
        sa.Column("date", sa.Date(), nullable=True),
    )
    op.execute("UPDATE global_indices SET date = issue_date WHERE date IS NULL")
    op.alter_column("global_indices", "date", nullable=False)
    op.drop_index("ix_global_indices_issue_date", table_name="global_indices")
    op.create_index("ix_global_indices_date", "global_indices", ["date"], unique=True)
    op.drop_column("global_indices", "issue_date")
    op.drop_column("global_indices", "source_url_oni")
    op.drop_column("global_indices", "source_url_mjo")
    op.drop_column("global_indices", "source_url_dmi")
    op.drop_column("model_versions", "is_trained")
