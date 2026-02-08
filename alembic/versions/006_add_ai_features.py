"""Add AI workbench tables: user_model_configs, chat_conversations, chat_messages, external_agents, web_browsing_results

Revision ID: 006
Revises: 004
Create Date: 2026-02-08
"""
from alembic import op
import sqlalchemy as sa

revision = '006'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade():
    # UserModelConfig — per-user, per-feature LLM configuration
    op.create_table(
        'user_model_configs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('feature_slot', sa.String(50), nullable=False),
        sa.Column('provider', sa.String(50), nullable=False),
        sa.Column('model', sa.String(200), nullable=False),
        sa.Column('api_key', sa.Text()),
        sa.Column('endpoint_url', sa.String(500)),
        sa.Column('extra_config', sa.JSON()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint('user_id', 'feature_slot', name='_user_feature_uc'),
    )

    # ExternalAgent — third-party agent registrations (create before chat_conversations due to FK)
    op.create_table(
        'external_agents',
        sa.Column('id', sa.Integer(), primary_key=True),
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

    # ChatConversation — conversation groupings
    op.create_table(
        'chat_conversations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('conversation_id', sa.String(64), unique=True, nullable=False, index=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('title', sa.String(255), server_default='New Chat'),
        sa.Column('feature', sa.String(50), server_default='chatbot'),
        sa.Column('agent_type', sa.String(50), server_default='direct_llm'),
        sa.Column('agent_id', sa.Integer(), sa.ForeignKey('external_agents.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # ChatMessage — persistent chat history
    op.create_table(
        'chat_messages',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('conversation_id', sa.String(64), sa.ForeignKey('chat_conversations.conversation_id'), nullable=False, index=True),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('metadata_json', sa.JSON()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # WebBrowsingResult — browsing history/cache
    op.create_table(
        'web_browsing_results',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('conversation_id', sa.String(64), nullable=True),
        sa.Column('query', sa.Text(), nullable=False),
        sa.Column('urls_fetched', sa.JSON()),
        sa.Column('extracted_content', sa.Text()),
        sa.Column('ai_summary', sa.Text()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table('web_browsing_results')
    op.drop_table('chat_messages')
    op.drop_table('chat_conversations')
    op.drop_table('external_agents')
    op.drop_table('user_model_configs')
