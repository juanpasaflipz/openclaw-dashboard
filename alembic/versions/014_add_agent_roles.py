"""Add agent_roles and team_rules tables for collaboration hierarchy.

Revision ID: 014
Revises: 013
Create Date: 2026-02-12
"""
from alembic import op
import sqlalchemy as sa

revision = '014'
down_revision = '013'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'agent_roles',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('workspace_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('agent_id', sa.Integer(), sa.ForeignKey('agents.id'), nullable=False),
        sa.Column('role', sa.String(20), nullable=False, server_default='worker'),
        sa.Column('can_assign_to_peers', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('can_escalate_to_supervisor', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('workspace_id', 'agent_id', name='uq_agent_role_ws_agent'),
    )
    op.create_index('ix_agent_role_ws', 'agent_roles', ['workspace_id'])

    op.create_table(
        'team_rules',
        sa.Column('workspace_id', sa.Integer(), sa.ForeignKey('users.id'), primary_key=True),
        sa.Column('allow_peer_assignment', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('require_supervisor_for_tasks', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('default_supervisor_agent_id', sa.Integer(), sa.ForeignKey('agents.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table('team_rules')
    op.drop_table('agent_roles')
