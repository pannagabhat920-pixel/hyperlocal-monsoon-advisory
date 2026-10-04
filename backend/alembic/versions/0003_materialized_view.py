"""create BlockForecastAgg materialized view

Revision ID: 0003
Revises: 0002
Create Date: 2024-01-03 00:00:00.000000

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # 1. Create materialized view aggregating grid forecasts to block level
    op.execute("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS block_forecast_agg AS
        SELECT
            b.id AS block_id,
            b.district_id,
            gf.issue_date,
            gf.lead_week,
            gf.target_week_start,
            gf.target_week_end,
            COUNT(gf.id)::int AS panchayat_count,
            ROUND(AVG(gf.onset_prob)::numeric, 4)::float AS avg_onset_prob,
            ROUND(AVG(gf.break_prob)::numeric, 4)::float AS avg_break_prob,
            ROUND(AVG(gf.excess_rain_prob)::numeric, 4)::float AS avg_excess_rain_prob,
            ROUND(AVG(gf.p10_rainfall_mm)::numeric, 2)::float AS avg_p10_rainfall_mm,
            ROUND(AVG(gf.p50_rainfall_mm)::numeric, 2)::float AS avg_p50_rainfall_mm,
            ROUND(AVG(gf.p90_rainfall_mm)::numeric, 2)::float AS avg_p90_rainfall_mm,
            ROUND(AVG(gf.confidence)::numeric, 4)::float AS avg_confidence,
            MODE() WITHIN GROUP (ORDER BY gf.data_source) AS data_source,
            MAX(gf.created_at) AS last_updated
        FROM grid_forecasts gf
        JOIN blocks b ON gf.block_id = b.id
        GROUP BY
            b.id,
            b.district_id,
            gf.issue_date,
            gf.lead_week,
            gf.target_week_start,
            gf.target_week_end;
    """)

    # 2. Create unique index to allow REFRESH MATERIALIZED VIEW CONCURRENTLY
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_block_forecast_agg 
        ON block_forecast_agg (block_id, issue_date, lead_week);
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_block_forecast_agg_district 
        ON block_forecast_agg (district_id, issue_date, lead_week);
    """)

def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS block_forecast_agg;")
