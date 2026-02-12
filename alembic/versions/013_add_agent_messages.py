"""Add agent_messages table for collaboration messaging.

Revision ID: 013
Revises: 012
Create Date: 2026-02-12
"""
from alembic import op
import sqlalchemy as sa

revision = '013'
down_revision = '012'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'agent_messages',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('workspace_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('task_id', sa.String(36), sa.ForeignKey('collaboration_tasks.id'), nullable=True),
        sa.Column('thread_id', sa.String(36), nullable=True),
        sa.Column('from_agent_id', sa.Integer(), sa.ForeignKey('agents.id'), nullable=True),
        sa.Column('to_agent_id', sa.Integer(), sa.ForeignKey('agents.id'), nullable=True),
        sa.Column('from_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('role', sa.String(10), nullable=False, server_default='agent'),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_agent_msg_task', 'agent_messages', ['task_id', 'created_at'])
    op.create_index('ix_agent_msg_thread', 'agent_messages', ['thread_id', 'created_at'])
    op.create_index('ix_agent_msg_ws', 'agent_messages', ['workspace_id', 'created_at'])


def downgrade():
    op.drop_table('agent_messages')
