"""add agent_actions table

Revision ID: 004
Revises: 003
Create Date: 2026-02-07

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime


# revision identifiers, used by Alembic.
revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade():
    # Create agent_actions table
    op.create_table(
        'agent_actions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('agent_id', sa.Integer(), nullable=True),
        sa.Column('action_type', sa.String(length=50), nullable=False),
        sa.Column('service_type', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('action_data', sa.Text(), nullable=False),
        sa.Column('ai_reasoning', sa.Text(), nullable=True),
        sa.Column('ai_confidence', sa.Float(), nullable=True),
        sa.Column('result_data', sa.Text(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.Column('executed_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ),
    )

    # Create indexes
    op.create_index(op.f('ix_agent_actions_action_type'), 'agent_actions', ['action_type'], unique=False)
    op.create_index(op.f('ix_agent_actions_status'), 'agent_actions', ['status'], unique=False)
    op.create_index(op.f('ix_agent_actions_created_at'), 'agent_actions', ['created_at'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_agent_actions_created_at'), table_name='agent_actions')
    op.drop_index(op.f('ix_agent_actions_status'), table_name='agent_actions')
    op.drop_index(op.f('ix_agent_actions_action_type'), table_name='agent_actions')
    op.drop_table('agent_actions')
