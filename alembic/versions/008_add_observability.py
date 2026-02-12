"""Add observability tables: obs_api_keys, obs_events, obs_runs,
obs_agent_daily_metrics, obs_alert_rules, obs_alert_events, obs_llm_pricing

Revision ID: 008
Revises: 006
Create Date: 2026-02-11
"""
from alembic import op
import sqlalchemy as sa

revision = '008'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade():
    # --- API keys for ingestion auth ---
    op.create_table(
        'obs_api_keys',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('key_hash', sa.String(64), unique=True, nullable=False),
        sa.Column('key_prefix', sa.String(12), nullable=False),
        sa.Column('name', sa.String(100), nullable=False, server_default='default'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('last_used_at', sa.DateTime()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_obs_api_keys_key_hash', 'obs_api_keys', ['key_hash'], unique=True)

    # --- Append-only event log ---
    op.create_table(
        'obs_events',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('uid', sa.String(36), unique=True, nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('agent_id', sa.Integer(), sa.ForeignKey('agents.id'), nullable=True),
        sa.Column('run_id', sa.String(36), nullable=True),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='info'),
        sa.Column('model', sa.String(200), nullable=True),
        sa.Column('tokens_in', sa.Integer(), nullable=True),
        sa.Column('tokens_out', sa.Integer(), nullable=True),
        sa.Column('cost_usd', sa.Numeric(12, 8), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('payload', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('dedupe_key', sa.String(255), nullable=True, unique=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_obs_events_uid', 'obs_events', ['uid'], unique=True)
    op.create_index('ix_obs_events_user_time', 'obs_events', ['user_id', 'created_at'])
    op.create_index('ix_obs_events_type', 'obs_events', ['event_type'])
    op.create_index('ix_obs_events_run_id', 'obs_events', ['run_id'])

    # --- Run tracking ---
    op.create_table(
        'obs_runs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('run_id', sa.String(36), unique=True, nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('agent_id', sa.Integer(), sa.ForeignKey('agents.id'), nullable=True),
        sa.Column('status', sa.String(20), server_default='running'),
        sa.Column('model', sa.String(200), nullable=True),
        sa.Column('total_tokens_in', sa.Integer(), server_default='0'),
        sa.Column('total_tokens_out', sa.Integer(), server_default='0'),
        sa.Column('total_cost_usd', sa.Numeric(12, 8), server_default='0'),
        sa.Column('total_latency_ms', sa.Integer(), server_default='0'),
        sa.Column('tool_calls_count', sa.Integer(), server_default='0'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('metadata_json', sa.JSON(), server_default='{}'),
        sa.Column('started_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_obs_runs_run_id', 'obs_runs', ['run_id'], unique=True)
    op.create_index('ix_obs_runs_user', 'obs_runs', ['user_id', 'started_at'])

    # --- Pre-aggregated daily metrics ---
    op.create_table(
        'obs_agent_daily_metrics',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('agent_id', sa.Integer(), sa.ForeignKey('agents.id'), nullable=True),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('total_runs', sa.Integer(), server_default='0'),
        sa.Column('successful_runs', sa.Integer(), server_default='0'),
        sa.Column('failed_runs', sa.Integer(), server_default='0'),
        sa.Column('total_events', sa.Integer(), server_default='0'),
        sa.Column('total_tokens_in', sa.Integer(), server_default='0'),
        sa.Column('total_tokens_out', sa.Integer(), server_default='0'),
        sa.Column('total_cost_usd', sa.Numeric(12, 8), server_default='0'),
        sa.Column('total_tool_calls', sa.Integer(), server_default='0'),
        sa.Column('tool_errors', sa.Integer(), server_default='0'),
        sa.Column('latency_p50_ms', sa.Integer(), nullable=True),
        sa.Column('latency_p95_ms', sa.Integer(), nullable=True),
        sa.Column('latency_avg_ms', sa.Integer(), nullable=True),
        sa.Column('models_used', sa.JSON(), server_default='{}'),
        sa.Column('last_heartbeat_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('user_id', 'agent_id', 'date', name='_obs_daily_uc'),
    )
    op.create_index('ix_obs_daily_lookup', 'obs_agent_daily_metrics', ['user_id', 'agent_id', 'date'])

    # --- Alert rules ---
    op.create_table(
        'obs_alert_rules',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('agent_id', sa.Integer(), sa.ForeignKey('agents.id'), nullable=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('rule_type', sa.String(50), nullable=False),
        sa.Column('threshold', sa.Numeric(12, 4), nullable=False),
        sa.Column('window_minutes', sa.Integer(), server_default='60'),
        sa.Column('cooldown_minutes', sa.Integer(), server_default='360'),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('last_triggered_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # --- Fired alert history ---
    op.create_table(
        'obs_alert_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('rule_id', sa.Integer(), sa.ForeignKey('obs_alert_rules.id'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('agent_id', sa.Integer(), sa.ForeignKey('agents.id'), nullable=True),
        sa.Column('metric_value', sa.Numeric(12, 4), nullable=False),
        sa.Column('threshold_value', sa.Numeric(12, 4), nullable=False),
        sa.Column('rule_type', sa.String(50), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('notified_slack', sa.Boolean(), server_default=sa.text('false')),
        sa.Column('acknowledged_at', sa.DateTime(), nullable=True),
        sa.Column('triggered_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_obs_alert_events_user', 'obs_alert_events', ['user_id', 'triggered_at'])

    # --- LLM pricing reference ---
    op.create_table(
        'obs_llm_pricing',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('provider', sa.String(50), nullable=False),
        sa.Column('model', sa.String(200), nullable=False),
        sa.Column('input_cost_per_mtok', sa.Numeric(10, 4), nullable=False),
        sa.Column('output_cost_per_mtok', sa.Numeric(10, 4), nullable=False),
        sa.Column('effective_from', sa.Date(), nullable=False),
        sa.Column('effective_to', sa.Date(), nullable=True),
        sa.UniqueConstraint('provider', 'model', 'effective_from', name='_obs_pricing_uc'),
    )


def downgrade():
    op.drop_table('obs_llm_pricing')
    op.drop_table('obs_alert_events')
    op.drop_table('obs_alert_rules')
    op.drop_table('obs_agent_daily_metrics')
    op.drop_table('obs_runs')
    op.drop_table('obs_events')
    op.drop_table('obs_api_keys')
