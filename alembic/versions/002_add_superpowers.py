"""add superpowers table

Revision ID: 002
Revises: 001
Create Date: 2026-02-06

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime


# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade():
    # Create superpowers table
    op.create_table(
        'superpowers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('agent_id', sa.Integer(), nullable=True),
        sa.Column('service_type', sa.String(length=50), nullable=False),
        sa.Column('service_name', sa.String(length=100), nullable=False),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('connected_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('last_used', sa.DateTime(), nullable=True),
        sa.Column('access_token_encrypted', sa.Text(), nullable=True),
        sa.Column('refresh_token_encrypted', sa.Text(), nullable=True),
        sa.Column('token_expires_at', sa.DateTime(), nullable=True),
        sa.Column('config', sa.Text(), nullable=True),
        sa.Column('scopes_granted', sa.Text(), nullable=True),
        sa.Column('usage_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ),
    )

    # Create indexes
    op.create_index(op.f('ix_superpowers_service_type'), 'superpowers', ['service_type'], unique=False)
    op.create_index(op.f('ix_superpowers_user_id'), 'superpowers', ['user_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_superpowers_user_id'), table_name='superpowers')
    op.drop_index(op.f('ix_superpowers_service_type'), table_name='superpowers')
    op.drop_table('superpowers')
