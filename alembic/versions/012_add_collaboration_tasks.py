"""Add collaboration_tasks and task_events tables.

Revision ID: 012
Revises: 011
Create Date: 2026-02-12
"""
from alembic import op
import sqlalchemy as sa

revision = '012'
down_revision = '011'
branch_labels = None
depends_on = None


def upgrade():
    # -- collaboration_tasks --
    op.create_table(
        'collaboration_tasks',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('workspace_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_by_agent_id', sa.Integer(), sa.ForeignKey('agents.id'), nullable=True),
        sa.Column('created_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('assigned_to_agent_id', sa.Integer(), sa.ForeignKey('agents.id'), nullable=False),
        sa.Column('parent_task_id', sa.String(36), sa.ForeignKey('collaboration_tasks.id'), nullable=True),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('input', sa.JSON(), nullable=True),
        sa.Column('output', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='queued'),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('due_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_collab_task_ws', 'collaboration_tasks', ['workspace_id'])
    op.create_index('ix_collab_task_ws_status', 'collaboration_tasks', ['workspace_id', 'status'])
    op.create_index('ix_collab_task_assigned', 'collaboration_tasks', ['assigned_to_agent_id', 'status'])
    op.create_index('ix_collab_task_parent', 'collaboration_tasks', ['parent_task_id'])

    # -- task_events --
    op.create_table(
        'task_events',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('task_id', sa.String(36), sa.ForeignKey('collaboration_tasks.id'), nullable=False),
        sa.Column('workspace_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('agent_id', sa.Integer(), sa.ForeignKey('agents.id'), nullable=True),
        sa.Column('event_type', sa.String(30), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_task_event_task_created', 'task_events', ['task_id', 'created_at'])
    op.create_index('ix_task_event_ws', 'task_events', ['workspace_id', 'created_at'])


def downgrade():
    op.drop_table('task_events')
    op.drop_table('collaboration_tasks')
