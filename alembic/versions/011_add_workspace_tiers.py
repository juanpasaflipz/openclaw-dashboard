"""Add workspace_tiers table for observability tier-based feature gating.

Revision ID: 011
Revises: 010
Create Date: 2026-02-11
"""
from alembic import op
import sqlalchemy as sa

revision = '011'
down_revision = '010'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'workspace_tiers',
        sa.Column('workspace_id', sa.Integer(), sa.ForeignKey('users.id'), primary_key=True),
        sa.Column('tier_name', sa.String(50), nullable=False, server_default='free'),
        sa.Column('agent_limit', sa.Integer(), nullable=False, server_default='2'),
        sa.Column('retention_days', sa.Integer(), nullable=False, server_default='7'),
        sa.Column('alert_rule_limit', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('health_history_days', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('anomaly_detection_enabled', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('slack_notifications_enabled', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('multi_workspace_enabled', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('priority_processing', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('max_api_keys', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('max_batch_size', sa.Integer(), nullable=False, server_default='100'),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )

    # Seed the four tier templates as workspace_id=0 reference rows are NOT needed.
    # Tiers are assigned per-workspace. Defaults live in WorkspaceTier.TIER_DEFAULTS
    # and are applied in code when no row exists (get_workspace_tier fallback).


def downgrade():
    op.drop_table('workspace_tiers')
