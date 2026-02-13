"""Merge external_agents into agents table.

Adds agent_type, connection_url, auth_config, agent_config, is_featured,
last_connected_at, last_error columns to agents. Migrates data from
external_agents, updates chat_conversations FK, and drops external_agents.

Revision ID: 015
Revises: 014
Create Date: 2026-02-12
"""
from alembic import op
import sqlalchemy as sa

revision = '015'
down_revision = '014'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Add new columns to agents table
    op.add_column('agents', sa.Column('agent_type', sa.String(50), nullable=False, server_default='direct'))
    op.add_column('agents', sa.Column('connection_url', sa.String(500), nullable=True))
    op.add_column('agents', sa.Column('auth_config', sa.JSON(), nullable=True))
    op.add_column('agents', sa.Column('agent_config', sa.JSON(), nullable=True))
    op.add_column('agents', sa.Column('is_featured', sa.Boolean(), nullable=True, server_default=sa.text('false')))
    op.add_column('agents', sa.Column('last_connected_at', sa.DateTime(), nullable=True))
    op.add_column('agents', sa.Column('last_error', sa.Text(), nullable=True))

    # 2. Migrate data from external_agents into agents
    conn = op.get_bind()

    # Check if external_agents table exists
    inspector = sa.inspect(conn)
    if 'external_agents' not in inspector.get_table_names():
        return  # Nothing to migrate

    rows = conn.execute(sa.text(
        "SELECT id, user_id, name, description, avatar_emoji, avatar_url, "
        "agent_type, connection_url, auth_config, agent_config, "
        "is_featured, is_active, last_connected_at, last_error, "
        "created_at, updated_at "
        "FROM external_agents"
    )).fetchall()

    id_map = {}  # old external_agents.id -> new agents.id
    for row in rows:
        old_id = row[0]
        # Insert into agents table
        result = conn.execute(sa.text(
            "INSERT INTO agents (user_id, name, description, avatar_emoji, avatar_url, "
            "agent_type, connection_url, auth_config, agent_config, "
            "is_featured, is_active, last_connected_at, last_error, "
            "created_at, updated_at) "
            "VALUES (:user_id, :name, :description, :avatar_emoji, :avatar_url, "
            ":agent_type, :connection_url, :auth_config, :agent_config, "
            ":is_featured, :is_active, :last_connected_at, :last_error, "
            ":created_at, :updated_at) "
            "RETURNING id"
        ), {
            'user_id': row[1],
            'name': row[2],
            'description': row[3],
            'avatar_emoji': row[4],
            'avatar_url': row[5],
            'agent_type': row[6],
            'connection_url': row[7],
            'auth_config': row[8],
            'agent_config': row[9],
            'is_featured': row[10],
            'is_active': row[11],
            'last_connected_at': row[12],
            'last_error': row[13],
            'created_at': row[14],
            'updated_at': row[15],
        })
        new_id = result.fetchone()[0]
        id_map[old_id] = new_id

    # 3. Update chat_conversations.agent_id references
    # First drop the old FK constraint
    try:
        op.drop_constraint('chat_conversations_agent_id_fkey', 'chat_conversations', type_='foreignkey')
    except Exception:
        pass  # Constraint may not exist or have a different name

    # Update agent_id values using the ID mapping
    for old_id, new_id in id_map.items():
        conn.execute(sa.text(
            "UPDATE chat_conversations SET agent_id = :new_id WHERE agent_id = :old_id"
        ), {'old_id': old_id, 'new_id': new_id})

    # Re-create FK pointing to agents
    op.create_foreign_key(
        'chat_conversations_agent_id_fkey',
        'chat_conversations', 'agents',
        ['agent_id'], ['id'],
    )

    # 4. Drop external_agents table
    op.drop_table('external_agents')


def downgrade():
    # Recreate external_agents table
    op.create_table(
        'external_agents',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('avatar_emoji', sa.String(10), server_default='🤖'),
        sa.Column('avatar_url', sa.String(500)),
        sa.Column('agent_type', sa.String(50), nullable=False, server_default='websocket'),
        sa.Column('connection_url', sa.String(500)),
        sa.Column('auth_config', sa.JSON()),
        sa.Column('agent_config', sa.JSON()),
        sa.Column('is_featured', sa.Boolean(), server_default=sa.text('false')),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true')),
        sa.Column('last_connected_at', sa.DateTime()),
        sa.Column('last_error', sa.Text()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # Remove added columns from agents
    op.drop_column('agents', 'last_error')
    op.drop_column('agents', 'last_connected_at')
    op.drop_column('agents', 'is_featured')
    op.drop_column('agents', 'agent_config')
    op.drop_column('agents', 'auth_config')
    op.drop_column('agents', 'connection_url')
    op.drop_column('agents', 'agent_type')
