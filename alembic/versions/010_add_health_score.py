"""Add obs_agent_health_daily table for agent health scores.

Revision ID: 010
Revises: 008
Create Date: 2026-02-11
"""
from alembic import op
import sqlalchemy as sa

revision = '010'
down_revision = '008'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'obs_agent_health_daily',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('agent_id', sa.Integer(), sa.ForeignKey('agents.id'), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('score', sa.Numeric(5, 2), nullable=False),
        sa.Column('success_rate_score', sa.Numeric(5, 2), nullable=False),
        sa.Column('latency_score', sa.Numeric(5, 2), nullable=False),
        sa.Column('error_burst_score', sa.Numeric(5, 2), nullable=False),
        sa.Column('cost_anomaly_score', sa.Numeric(5, 2), nullable=False),
        sa.Column('details', sa.JSON(), server_default='{}'),
        sa.Column('computed_at', sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint('user_id', 'agent_id', 'date', name='_obs_health_daily_uc'),
    )
    op.create_index('ix_obs_health_daily_lookup', 'obs_agent_health_daily',
                     ['user_id', 'agent_id', 'date'])


def downgrade():
    op.drop_table('obs_agent_health_daily')
