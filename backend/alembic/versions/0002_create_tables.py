"""create all core tables and indexes

Revision ID: 0002
Revises: 0001
Create Date: 2024-01-02 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geometry

# revision identifiers, used by Alembic.
revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None

# Pre-declare all enum types with create_type=False so that
# op.create_table() never tries to auto-CREATE TYPE; we call
# .create(..., checkfirst=True) explicitly before each table group.
user_role_enum = sa.Enum('FARMER', 'EXTENSION_OFFICER', 'ADMIN', name='userrole', create_type=False)
irrigation_source_enum = sa.Enum('RAINFED', 'CANAL', 'BOREWELL', 'TANK', 'OTHER', name='irrigationsource', create_type=False)
data_source_enum = sa.Enum('LIVE', 'HINDCAST', 'SIMULATED', name='datasource', create_type=False)
advisory_severity_enum = sa.Enum('INFO', 'ADVISORY', 'HIGH', 'CRITICAL', name='advisoryseverity', create_type=False)
advisory_approval_status_enum = sa.Enum('PENDING', 'APPROVED', 'REJECTED', 'AUTO_APPROVED', name='advisoryapprovalstatus', create_type=False)
notification_channel_enum = sa.Enum('WHATSAPP', 'SMS', 'PUSH', name='notificationchannel', create_type=False)
notification_status_enum = sa.Enum('QUEUED', 'SENT', 'DELIVERED', 'FAILED', 'BLOCKED_SIMULATED', name='notificationstatus', create_type=False)


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Geography tables (no enums)
    op.create_table(
        'states',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('lgd_code', sa.Integer(), nullable=True),
        sa.Column('geom', Geometry(geometry_type='MULTIPOLYGON', srid=4326, spatial_index=True), nullable=True),
        sa.Column('is_synthetic_boundary', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('lgd_code')
    )
    op.create_index('ix_states_name', 'states', ['name'])

    op.create_table(
        'districts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('state_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('lgd_code', sa.Integer(), nullable=True),
        sa.Column('geom', Geometry(geometry_type='MULTIPOLYGON', srid=4326, spatial_index=True), nullable=True),
        sa.Column('is_synthetic_boundary', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.ForeignKeyConstraint(['state_id'], ['states.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('lgd_code')
    )
    op.create_index('ix_districts_state_id', 'districts', ['state_id'])
    op.create_index('ix_districts_name', 'districts', ['name'])

    op.create_table(
        'blocks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('district_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('lgd_code', sa.Integer(), nullable=True),
        sa.Column('geom', Geometry(geometry_type='MULTIPOLYGON', srid=4326, spatial_index=True), nullable=True),
        sa.Column('is_synthetic_boundary', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.ForeignKeyConstraint(['district_id'], ['districts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('lgd_code')
    )
    op.create_index('ix_blocks_district_id', 'blocks', ['district_id'])
    op.create_index('ix_blocks_name', 'blocks', ['name'])

    op.create_table(
        'panchayats',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('block_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('lgd_code', sa.Integer(), nullable=True),
        sa.Column('geom', Geometry(geometry_type='MULTIPOLYGON', srid=4326, spatial_index=True), nullable=True),
        sa.Column('centroid', Geometry(geometry_type='POINT', srid=4326, spatial_index=True), nullable=True),
        sa.Column('is_synthetic_boundary', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.ForeignKeyConstraint(['block_id'], ['blocks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('lgd_code')
    )
    op.create_index('ix_panchayats_block_id', 'panchayats', ['block_id'])
    op.create_index('ix_panchayats_name', 'panchayats', ['name'])
    op.create_index('ix_panchayats_block_id_name', 'panchayats', ['block_id', 'name'])

    # 2. Users tables
    sa.Enum('FARMER', 'EXTENSION_OFFICER', 'ADMIN', name='userrole').create(bind, checkfirst=True)
    sa.Enum('RAINFED', 'CANAL', 'BOREWELL', 'TANK', 'OTHER', name='irrigationsource').create(bind, checkfirst=True)

    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('phone_number', sa.String(length=20), nullable=False),
        sa.Column('role', user_role_enum, server_default='FARMER', nullable=False),
        sa.Column('preferred_language', sa.String(length=10), server_default='en', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('consent_given_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('phone_number')
    )
    op.create_index('ix_users_phone_number', 'users', ['phone_number'])
    op.create_index('ix_users_role', 'users', ['role'])

    op.create_table(
        'farmer_profiles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('panchayat_id', sa.Integer(), nullable=True),
        sa.Column('crop_type', sa.String(length=100), nullable=False),
        sa.Column('sowing_date', sa.Date(), nullable=True),
        sa.Column('soil_type', sa.String(length=50), nullable=True),
        sa.Column('irrigation_source', irrigation_source_enum, server_default='RAINFED', nullable=False),
        sa.Column('farm_size_acres', sa.Float(), nullable=True),
        sa.Column('crop_status', sa.String(length=50), server_default='PLANNED', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['panchayat_id'], ['panchayats.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id')
    )
    op.create_index('ix_farmer_profiles_panchayat_id', 'farmer_profiles', ['panchayat_id'])

    op.create_table(
        'officer_jurisdictions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('district_id', sa.Integer(), nullable=True),
        sa.Column('block_id', sa.Integer(), nullable=True),
        sa.Column('assigned_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['block_id'], ['blocks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['district_id'], ['districts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_officer_jurisdictions_user_id', 'officer_jurisdictions', ['user_id'])
    op.create_index('ix_officer_jurisdictions_block_id', 'officer_jurisdictions', ['block_id'])

    op.create_table(
        'otp_verifications',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('phone_number', sa.String(length=20), nullable=False),
        sa.Column('otp_hash', sa.String(length=255), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('attempts', sa.Integer(), server_default='0', nullable=False),
        sa.Column('is_verified', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_otp_verifications_phone_number', 'otp_verifications', ['phone_number'])

    op.create_table(
        'refresh_tokens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('token_hash', sa.String(length=255), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token_hash')
    )
    op.create_index('ix_refresh_tokens_user_id', 'refresh_tokens', ['user_id'])

    op.create_table(
        'audit_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('resource_type', sa.String(length=100), nullable=False),
        sa.Column('resource_id', sa.String(length=100), nullable=True),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('ip_address', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_audit_logs_user_id', 'audit_logs', ['user_id'])
    op.create_index('ix_audit_logs_action', 'audit_logs', ['action'])

    # 3. Climate tables
    sa.Enum('LIVE', 'HINDCAST', 'SIMULATED', name='datasource').create(bind, checkfirst=True)

    op.create_table(
        'global_indices',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('nino34', sa.Float(), nullable=False),
        sa.Column('iod_dmi', sa.Float(), nullable=False),
        sa.Column('mjo_phase', sa.Integer(), nullable=False),
        sa.Column('mjo_amplitude', sa.Float(), nullable=False),
        sa.Column('data_source', data_source_enum, server_default='LIVE', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('date')
    )
    op.create_index('ix_global_indices_date', 'global_indices', ['date'])

    op.create_table(
        'model_versions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('version_tag', sa.String(length=50), nullable=False),
        sa.Column('model_type', sa.String(length=50), nullable=False),
        sa.Column('trained_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('metrics_json', sa.JSON(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('version_tag')
    )

    op.create_table(
        'grid_forecasts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('panchayat_id', sa.Integer(), nullable=False),
        sa.Column('block_id', sa.Integer(), nullable=False),
        sa.Column('issue_date', sa.Date(), nullable=False),
        sa.Column('target_week_start', sa.Date(), nullable=False),
        sa.Column('target_week_end', sa.Date(), nullable=False),
        sa.Column('lead_week', sa.Integer(), nullable=False),
        sa.Column('onset_prob', sa.Float(), nullable=False),
        sa.Column('break_prob', sa.Float(), nullable=False),
        sa.Column('excess_rain_prob', sa.Float(), nullable=False),
        sa.Column('p10_rainfall_mm', sa.Float(), nullable=False),
        sa.Column('p50_rainfall_mm', sa.Float(), nullable=False),
        sa.Column('p90_rainfall_mm', sa.Float(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('data_source', data_source_enum, server_default='SIMULATED', nullable=False),
        sa.Column('model_version_id', sa.Integer(), nullable=True),
        sa.Column('features_json', sa.JSON(), nullable=True),
        sa.Column('shap_values_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['block_id'], ['blocks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['model_version_id'], ['model_versions.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['panchayat_id'], ['panchayats.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_grid_forecasts_panchayat_id', 'grid_forecasts', ['panchayat_id'])
    op.create_index('ix_grid_forecasts_block_id', 'grid_forecasts', ['block_id'])
    op.create_index('ix_grid_forecasts_issue_date', 'grid_forecasts', ['issue_date'])
    op.create_index('ix_grid_forecasts_lead_week', 'grid_forecasts', ['lead_week'])
    op.create_index('ix_grid_forecasts_data_source', 'grid_forecasts', ['data_source'])
    op.create_index('ix_grid_forecasts_panchayat_issue_lead', 'grid_forecasts', ['panchayat_id', 'issue_date', 'lead_week'])
    op.create_index('ix_grid_forecasts_block_issue_lead', 'grid_forecasts', ['block_id', 'issue_date', 'lead_week'])

    # 4. Agronomy tables
    sa.Enum('INFO', 'ADVISORY', 'HIGH', 'CRITICAL', name='advisoryseverity').create(bind, checkfirst=True)
    sa.Enum('PENDING', 'APPROVED', 'REJECTED', 'AUTO_APPROVED', name='advisoryapprovalstatus').create(bind, checkfirst=True)
    sa.Enum('WHATSAPP', 'SMS', 'PUSH', name='notificationchannel').create(bind, checkfirst=True)
    sa.Enum('QUEUED', 'SENT', 'DELIVERED', 'FAILED', 'BLOCKED_SIMULATED', name='notificationstatus').create(bind, checkfirst=True)

    op.create_table(
        'agronomic_rules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('rule_code', sa.String(length=50), nullable=False),
        sa.Column('crop_type', sa.String(length=50), nullable=False),
        sa.Column('growth_stage', sa.String(length=50), nullable=False),
        sa.Column('trigger_condition_json', sa.JSON(), nullable=False),
        sa.Column('advisory_template_en', sa.Text(), nullable=False),
        sa.Column('advisory_template_local', sa.JSON(), nullable=True),
        sa.Column('severity', advisory_severity_enum, nullable=False),
        sa.Column('action_type', sa.String(length=50), nullable=False),
        sa.Column('source_reference', sa.String(length=255), nullable=False),
        sa.Column('is_approved', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('version', sa.Integer(), server_default='1', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('rule_code')
    )
    op.create_index('ix_agronomic_rules_crop_type', 'agronomic_rules', ['crop_type'])
    op.create_index('ix_agronomic_rules_severity', 'agronomic_rules', ['severity'])

    op.create_table(
        'generated_advisories',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('panchayat_id', sa.Integer(), nullable=False),
        sa.Column('block_id', sa.Integer(), nullable=False),
        sa.Column('forecast_id', sa.Integer(), nullable=False),
        sa.Column('rule_id', sa.Integer(), nullable=False),
        sa.Column('crop_type', sa.String(length=50), nullable=False),
        sa.Column('language', sa.String(length=10), server_default='en', nullable=False),
        sa.Column('headline', sa.String(length=255), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('audio_url', sa.String(length=255), nullable=True),
        sa.Column('severity', advisory_severity_enum, nullable=False),
        sa.Column('approval_status', advisory_approval_status_enum, server_default='PENDING', nullable=False),
        sa.Column('approved_by_officer_id', sa.Integer(), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('data_source', data_source_enum, server_default='SIMULATED', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['approved_by_officer_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['block_id'], ['blocks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['forecast_id'], ['grid_forecasts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['panchayat_id'], ['panchayats.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['rule_id'], ['agronomic_rules.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_generated_advisories_panchayat_id', 'generated_advisories', ['panchayat_id'])
    op.create_index('ix_generated_advisories_block_id', 'generated_advisories', ['block_id'])
    op.create_index('ix_generated_advisories_crop_type', 'generated_advisories', ['crop_type'])
    op.create_index('ix_generated_advisories_severity', 'generated_advisories', ['severity'])
    op.create_index('ix_generated_advisories_approval_status', 'generated_advisories', ['approval_status'])
    op.create_index('ix_generated_advisories_block_status', 'generated_advisories', ['block_id', 'approval_status'])

    op.create_table(
        'notification_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('advisory_id', sa.Integer(), nullable=False),
        sa.Column('recipient_user_id', sa.Integer(), nullable=False),
        sa.Column('channel', notification_channel_enum, server_default='SMS', nullable=False),
        sa.Column('message_content', sa.Text(), nullable=False),
        sa.Column('dispatch_status', notification_status_enum, server_default='QUEUED', nullable=False),
        sa.Column('provider_message_id', sa.String(length=100), nullable=True),
        sa.Column('attempt_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('idempotency_key', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['advisory_id'], ['generated_advisories.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['recipient_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('idempotency_key')
    )
    op.create_index('ix_notification_logs_advisory_id', 'notification_logs', ['advisory_id'])
    op.create_index('ix_notification_logs_recipient_user_id', 'notification_logs', ['recipient_user_id'])
    op.create_index('ix_notification_logs_dispatch_status', 'notification_logs', ['dispatch_status'])


def downgrade() -> None:
    op.drop_table('notification_logs')
    op.drop_table('generated_advisories')
    op.drop_table('agronomic_rules')
    op.drop_table('grid_forecasts')
    op.drop_table('model_versions')
    op.drop_table('global_indices')
    op.drop_table('audit_logs')
    op.drop_table('refresh_tokens')
    op.drop_table('otp_verifications')
    op.drop_table('officer_jurisdictions')
    op.drop_table('farmer_profiles')
    op.drop_table('users')
    op.drop_table('panchayats')
    op.drop_table('blocks')
    op.drop_table('districts')
    op.drop_table('states')
    # Drop enum types
    sa.Enum(name='notificationstatus').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='notificationchannel').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='advisoryapprovalstatus').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='advisoryseverity').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='datasource').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='irrigationsource').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='userrole').drop(op.get_bind(), checkfirst=True)
