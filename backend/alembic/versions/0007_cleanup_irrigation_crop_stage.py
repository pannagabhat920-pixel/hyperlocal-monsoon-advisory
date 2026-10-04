"""Align CropStage and cleanup duplicate IrrigationSource

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-04 17:55:00
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0007'
down_revision: Union[str, None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # 1. Update duplicate irrigation sources in farmer_profiles
    op.execute("UPDATE farmer_profiles SET irrigation_source = 'BOREWELL_WELL' WHERE irrigation_source::text = 'BOREWELL';")
    op.execute("UPDATE farmer_profiles SET irrigation_source = 'TANK_POND' WHERE irrigation_source::text = 'TANK';")

    # 2. Update legacy crop statuses in farmer_profiles to the canonical 5 stages:
    # NOT_STARTED, SOWN, VEGETATIVE, FLOWERING_PODDING, HARVEST_READY
    op.execute("UPDATE farmer_profiles SET crop_status = 'NOT_STARTED' WHERE crop_status IN ('PLANNED', 'unknown');")
    op.execute("UPDATE farmer_profiles SET crop_status = 'FLOWERING_PODDING' WHERE crop_status IN ('FLOWERING', 'TRANSPLANTING', 'GRAIN_FILLING');")
    op.execute("UPDATE farmer_profiles SET crop_status = 'HARVEST_READY' WHERE crop_status IN ('HARVESTING', 'HARVESTED');")
    op.execute("ALTER TABLE farmer_profiles ALTER COLUMN crop_status SET DEFAULT 'NOT_STARTED';")

def downgrade() -> None:
    pass
