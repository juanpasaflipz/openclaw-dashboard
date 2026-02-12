"""
Database models for OpenClaw Dashboard monetization
"""
from datetime import datetime, timedelta
from flask_sqlalchemy import SQLAlchemy
import secrets
import hashlib

db = SQLAlchemy()


class User(db.Model):
    """User account with email-based authentication"""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

    # Admin access control
    is_admin = db.Column(db.Boolean, default=False, nullable=False, index=True)

    # Credits for Moltbook posting
    credit_balance = db.Column(db.Integer, default=0)

    # Stripe integration
    stripe_customer_id = db.Column(db.String(255), unique=True, index=True)

    # Subscription tier: 'free', 'pro' (legacy: 'starter', 'team' mapped via effective_tier)
    subscription_tier = db.Column(db.String(50), default='free', index=True)
    subscription_status = db.Column(db.String(50), default='inactive')  # 'active', 'inactive', 'cancelled', 'past_due'
    stripe_subscription_id = db.Column(db.String(255), unique=True, index=True)
    subscription_expires_at = db.Column(db.DateTime)  # For tracking expiry
    subscription_started_at = db.Column(db.DateTime)

    # Relationships
    transactions = db.relationship('CreditTransaction', backref='user', lazy='dynamic')
    magic_links = db.relationship('MagicLink', backref='user', lazy='dynamic')
    post_history = db.relationship('PostHistory', backref='user', lazy='dynamic')
    agents = db.relationship('Agent', backref='user', lazy='dynamic')

    def __repr__(self):
        return f'<User {self.email}>'

    def has_credits(self, amount=1):
        """Check if user has enough credits"""
        return self.credit_balance >= amount

    def deduct_credits(self, amount=1, reason='post'):
        """Deduct credits and record transaction"""
        if not self.has_credits(amount):
            return False

        self.credit_balance -= amount
        transaction = CreditTransaction(
            user_id=self.id,
            amount=-amount,
            transaction_type='debit',
            reason=reason
        )
        db.session.add(transaction)
        return True

    def add_credits(self, amount, reason='purchase', stripe_payment_id=None):
        """Add credits and record transaction"""
        self.credit_balance += amount
        transaction = CreditTransaction(
            user_id=self.id,
            amount=amount,
            transaction_type='credit',
            reason=reason,
            stripe_payment_id=stripe_payment_id
        )
        db.session.add(transaction)

    @property
    def effective_tier(self):
        """Map legacy tiers to the simplified 2-tier model (free/pro).
        Existing 'starter' and 'team' users are treated as 'pro'."""
        if self.subscription_tier in ('starter', 'team'):
            return 'pro'
        return self.subscription_tier

    def has_active_subscription(self):
        """Check if user has an active subscription"""
        if self.subscription_status != 'active':
            return False
        if self.subscription_expires_at and datetime.utcnow() > self.subscription_expires_at:
            return False
        return True

    def is_premium(self):
        """Check if user has premium features (Pro tier)"""
        return self.has_active_subscription() and self.effective_tier == 'pro'

    def has_unlimited_posts(self):
        """Check if user has unlimited posting (no rate limit)"""
        if self.is_admin:
            return True
        return self.is_premium()

    def get_max_agents(self):
        """Get max number of agents user can have"""
        if self.effective_tier == 'pro' and self.has_active_subscription():
            return 999  # Unlimited
        return 1  # Free tier

    def can_access_feed(self):
        """Check if user can access Moltbook feed (Pro)"""
        if self.is_admin:
            return True
        return self.is_premium()

    def can_upvote(self):
        """Check if user can upvote posts (Pro)"""
        if self.is_admin:
            return True
        return self.is_premium()

    def can_view_profiles(self):
        """Check if user can view other agent profiles (Pro)"""
        if self.is_admin:
            return True
        return self.is_premium()

    def can_access_analytics(self):
        """Check if user can access analytics dashboard (Pro)"""
        if self.is_admin:
            return True
        return self.is_premium()

    def can_access_personal_feed(self):
        """Check if user can access personalized feed (Pro)"""
        if self.is_admin:
            return True
        return self.is_premium()

    def get_primary_agent(self):
        """Get user's first agent (for API calls)"""
        return self.agents.first()


class MagicLink(db.Model):
    """Magic link tokens for passwordless authentication"""
    __tablename__ = 'magic_links'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    token = db.Column(db.String(255), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.DateTime)
    ip_address = db.Column(db.String(45))  # IPv6 compatible

    def __repr__(self):
        return f'<MagicLink {self.token[:8]}...>'

    @staticmethod
    def generate_token():
        """Generate a secure random token"""
        return secrets.token_urlsafe(32)

    @classmethod
    def create_for_user(cls, user_id, expires_in_minutes=15):
        """Create a new magic link for a user"""
        token = cls.generate_token()
        magic_link = cls(
            user_id=user_id,
            token=token,
            expires_at=datetime.utcnow() + timedelta(minutes=expires_in_minutes)
        )
        db.session.add(magic_link)
        return magic_link

    def is_valid(self):
        """Check if magic link is still valid"""
        if self.used_at is not None:
            return False
        if datetime.utcnow() > self.expires_at:
            return False
        return True

    def mark_as_used(self):
        """Mark magic link as used"""
        self.used_at = datetime.utcnow()


class CreditTransaction(db.Model):
    """Record of credit purchases and usage"""
    __tablename__ = 'credit_transactions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    amount = db.Column(db.Integer, nullable=False)  # Positive for credits added, negative for used
    transaction_type = db.Column(db.String(50), nullable=False)  # 'credit' or 'debit'
    reason = db.Column(db.String(255))  # 'purchase', 'post', 'refund', etc.
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Stripe integration
    stripe_payment_id = db.Column(db.String(255), index=True)
    stripe_checkout_session_id = db.Column(db.String(255), index=True)

    def __repr__(self):
        return f'<CreditTransaction user_id={self.user_id} amount={self.amount}>'


class PostHistory(db.Model):
    """Track Moltbook posts made through the dashboard"""
    __tablename__ = 'post_history'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Post details
    post_title = db.Column(db.String(500))
    post_submolt = db.Column(db.String(100))
    post_content_length = db.Column(db.Integer)

    # Moltbook response
    moltbook_post_id = db.Column(db.String(255))
    success = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f'<PostHistory user_id={self.user_id} title="{self.post_title[:30]}">'


class CreditPackage(db.Model):
    """Available credit packages for purchase"""
    __tablename__ = 'credit_packages'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    credits = db.Column(db.Integer, nullable=False)
    price_cents = db.Column(db.Integer, nullable=False)  # Price in cents (e.g., 500 = $5.00)
    stripe_price_id = db.Column(db.String(255), unique=True, index=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<CreditPackage {self.name} - {self.credits} credits for ${self.price_cents/100:.2f}>'

    @property
    def price_dollars(self):
        """Get price in dollars"""
        return self.price_cents / 100


class SubscriptionPlan(db.Model):
    """Available subscription plans/tiers"""
    __tablename__ = 'subscription_plans'

    id = db.Column(db.Integer, primary_key=True)
    tier = db.Column(db.String(50), unique=True, nullable=False)  # 'starter', 'pro', 'team'
    name = db.Column(db.String(100), nullable=False)
    price_monthly_cents = db.Column(db.Integer, nullable=False)
    stripe_price_id = db.Column(db.String(255), unique=True, index=True)
    stripe_product_id = db.Column(db.String(255), index=True)

    # Features
    unlimited_posts = db.Column(db.Boolean, default=False)
    max_agents = db.Column(db.Integer, default=1)
    scheduled_posting = db.Column(db.Boolean, default=False)
    analytics = db.Column(db.Boolean, default=False)
    api_access = db.Column(db.Boolean, default=False)
    team_members = db.Column(db.Integer, default=1)
    priority_support = db.Column(db.Boolean, default=False)

    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<SubscriptionPlan {self.name} - ${self.price_monthly_cents/100:.2f}/month>'

    @property
    def price_monthly_dollars(self):
        """Get monthly price in dollars"""
        return self.price_monthly_cents / 100


class ConfigFile(db.Model):
    """Store configuration files in database (for serverless compatibility)"""
    __tablename__ = 'config_files'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    filename = db.Column(db.String(100), nullable=False)  # e.g., 'LLM_CONFIG.md'
    content = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Unique constraint: one config file per user per filename
    __table_args__ = (db.UniqueConstraint('user_id', 'filename', name='_user_filename_uc'),)

    def __repr__(self):
        return f'<ConfigFile user_id={self.user_id} filename={self.filename}>'


class Agent(db.Model):
    """User's AI agent configuration"""
    __tablename__ = 'agents'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # Agent identity
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    avatar_emoji = db.Column(db.String(10), default='🤖')
    avatar_url = db.Column(db.String(500))  # Moltbook avatar URL
    personality = db.Column(db.Text)  # Agent personality/bio

    # Moltbook integration
    moltbook_api_key = db.Column(db.String(255))  # API key for Moltbook access

    # Status
    is_active = db.Column(db.Boolean, default=True)
    is_default = db.Column(db.Boolean, default=False)  # User's default agent

    # Configuration stored as JSON
    llm_config = db.Column(db.JSON)  # {provider, model, api_key, temperature, etc.}
    identity_config = db.Column(db.JSON)  # {personality, role, behavior, etc.}
    moltbook_config = db.Column(db.JSON)  # {api_key, default_submolt, etc.}

    # Usage statistics
    total_posts = db.Column(db.Integer, default=0)
    last_post_at = db.Column(db.DateTime)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<Agent {self.name} (user_id={self.user_id})>'

    def to_dict(self):
        """Convert agent to dictionary for API responses"""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'avatar_emoji': self.avatar_emoji,
            'is_active': self.is_active,
            'is_default': self.is_default,
            'total_posts': self.total_posts,
            'last_post_at': self.last_post_at.isoformat() if self.last_post_at else None,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }


# ============================================
# Phase 1: Feed + Analytics Models
# ============================================

class MoltbookFeedCache(db.Model):
    """Cache for Moltbook feed data"""
    __tablename__ = 'moltbook_feed_cache'

    id = db.Column(db.Integer, primary_key=True)
    feed_type = db.Column(db.String(50), nullable=False)  # 'global', 'submolt', 'personal'
    feed_key = db.Column(db.String(255))  # submolt name if feed_type='submolt'
    sort_type = db.Column(db.String(20), nullable=False)  # 'hot', 'new', 'top', 'rising'
    post_data = db.Column(db.Text, nullable=False)  # JSON of post
    cached_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)


class UserUpvote(db.Model):
    """Track user upvotes on Moltbook posts"""
    __tablename__ = 'user_upvotes'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    agent_id = db.Column(db.Integer, db.ForeignKey('agents.id'), nullable=False)
    moltbook_post_id = db.Column(db.String(255), nullable=False)
    upvoted_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    user = db.relationship('User', backref='upvotes')
    agent = db.relationship('Agent', backref='upvotes')


class AnalyticsSnapshot(db.Model):
    """Daily analytics snapshots for historical tracking"""
    __tablename__ = 'analytics_snapshots'

    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.Integer, db.ForeignKey('agents.id'), nullable=False)
    snapshot_date = db.Column(db.Date, nullable=False)
    karma = db.Column(db.Integer, default=0)
    total_posts = db.Column(db.Integer, default=0)
    total_comments = db.Column(db.Integer, default=0)
    followers = db.Column(db.Integer, default=0)
    following = db.Column(db.Integer, default=0)

    # Relationship
    agent = db.relationship('Agent', backref='analytics_snapshots')


class PostAnalytics(db.Model):
    """Track individual post performance"""
    __tablename__ = 'post_analytics'

    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.Integer, db.ForeignKey('agents.id'), nullable=False)
    moltbook_post_id = db.Column(db.String(255), nullable=False)
    title = db.Column(db.Text)
    submolt = db.Column(db.String(255))
    upvotes = db.Column(db.Integer, default=0)
    downvotes = db.Column(db.Integer, default=0)
    comment_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime)
    last_synced = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship
    agent = db.relationship('Agent', backref='post_analytics')


class Superpower(db.Model):
    """Track connected external services (Gmail, Calendar, Drive, etc.)"""
    __tablename__ = 'superpowers'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    agent_id = db.Column(db.Integer, db.ForeignKey('agents.id'), nullable=True)  # Nullable for user-level connections

    # Service identification
    service_type = db.Column(db.String(50), nullable=False, index=True)  # 'gmail', 'google_calendar', 'google_drive', etc.
    service_name = db.Column(db.String(100), nullable=False)  # Display name
    category = db.Column(db.String(50), nullable=False)  # 'connect', 'know', 'do', 'automate', 'protect', 'scale'

    # Connection status
    is_enabled = db.Column(db.Boolean, default=True, nullable=False)
    connected_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_used = db.Column(db.DateTime)

    # OAuth tokens (stored encrypted)
    access_token_encrypted = db.Column(db.Text)  # Encrypted OAuth access token
    refresh_token_encrypted = db.Column(db.Text)  # Encrypted OAuth refresh token
    token_expires_at = db.Column(db.DateTime)

    # Service-specific configuration (JSON)
    config = db.Column(db.Text)  # JSON blob for service-specific settings

    # Permission scopes granted
    scopes_granted = db.Column(db.Text)  # JSON array of OAuth scopes

    # Usage tracking
    usage_count = db.Column(db.Integer, default=0)
    last_error = db.Column(db.Text)  # Store last error for debugging

    # Relationships
    user = db.relationship('User', backref='superpowers')
    agent = db.relationship('Agent', backref='superpowers')

    def __repr__(self):
        return f'<Superpower {self.service_type} for User {self.user_id}>'


class AgentAction(db.Model):
    """Approval queue for AI agent actions that require user consent"""
    __tablename__ = 'agent_actions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    agent_id = db.Column(db.Integer, db.ForeignKey('agents.id'), nullable=True)

    # Action details
    action_type = db.Column(db.String(50), nullable=False, index=True)  # 'send_email', 'draft_reply', 'categorize', etc.
    service_type = db.Column(db.String(50), nullable=False)  # 'gmail', 'google_calendar', etc.

    # Action status
    status = db.Column(db.String(20), default='pending', index=True)  # 'pending', 'approved', 'rejected', 'executed', 'failed'

    # Payload (JSON)
    action_data = db.Column(db.Text, nullable=False)  # JSON with action parameters (to, subject, body, etc.)

    # AI context
    ai_reasoning = db.Column(db.Text)  # Why the AI wants to take this action
    ai_confidence = db.Column(db.Float)  # Confidence score 0-1

    # Result tracking
    result_data = db.Column(db.Text)  # JSON with execution results
    error_message = db.Column(db.Text)  # Error if execution failed

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    approved_at = db.Column(db.DateTime)
    executed_at = db.Column(db.DateTime)

    # Relationships
    user = db.relationship('User', backref='agent_actions')
    agent = db.relationship('Agent', backref='agent_actions')

    def __repr__(self):
        return f'<AgentAction {self.action_type} ({self.status})>'

    def to_dict(self):
        """Convert action to dictionary for API responses"""
        import json
        return {
            'id': self.id,
            'action_type': self.action_type,
            'service_type': self.service_type,
            'status': self.status,
            'action_data': json.loads(self.action_data) if self.action_data else {},
            'ai_reasoning': self.ai_reasoning,
            'ai_confidence': self.ai_confidence,
            'result_data': json.loads(self.result_data) if self.result_data else {},
            'error_message': self.error_message,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'approved_at': self.approved_at.isoformat() if self.approved_at else None,
            'executed_at': self.executed_at.isoformat() if self.executed_at else None,
            'agent': {
                'id': self.agent.id,
                'name': self.agent.name,
                'avatar_emoji': self.agent.avatar_emoji
            } if self.agent else None
        }


# ============================================
# AI Workbench Models
# ============================================

class UserModelConfig(db.Model):
    """Per-user, per-feature LLM configuration"""
    __tablename__ = 'user_model_configs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    feature_slot = db.Column(db.String(50), nullable=False)  # 'chatbot', 'web_browsing', 'utility', or custom tool name

    # LLM config
    provider = db.Column(db.String(50), nullable=False)  # 'openai', 'anthropic', 'google', 'groq', etc.
    model = db.Column(db.String(200), nullable=False)
    api_key = db.Column(db.Text)  # Encrypted in production
    endpoint_url = db.Column(db.String(500))  # Custom endpoint URL
    extra_config = db.Column(db.JSON)  # {temperature, max_tokens, etc.}

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('user_id', 'feature_slot', name='_user_feature_uc'),)

    user = db.relationship('User', backref='model_configs')

    def to_dict(self):
        return {
            'id': self.id,
            'feature_slot': self.feature_slot,
            'provider': self.provider,
            'model': self.model,
            'has_api_key': bool(self.api_key),
            'endpoint_url': self.endpoint_url,
            'extra_config': self.extra_config or {},
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class ChatConversation(db.Model):
    """Chat conversation groupings"""
    __tablename__ = 'chat_conversations'

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.String(64), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(255), default='New Chat')

    # What feature/agent this conversation belongs to
    feature = db.Column(db.String(50), default='chatbot')  # chatbot, web_browsing, utility, nautilus
    agent_type = db.Column(db.String(50), default='direct_llm')  # direct_llm, nautilus, external
    agent_id = db.Column(db.Integer, db.ForeignKey('external_agents.id'), nullable=True)

    # Channel linking (Telegram, Discord, etc.)
    channel_platform = db.Column(db.String(50), index=True)  # 'telegram', 'discord', etc.
    channel_chat_id = db.Column(db.String(255), index=True)  # External chat ID
    channel_metadata = db.Column(db.JSON)  # Platform-specific data (username, etc.)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', backref='chat_conversations')
    messages = db.relationship('ChatMessage', backref='conversation', lazy='dynamic', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'conversation_id': self.conversation_id,
            'title': self.title,
            'feature': self.feature,
            'agent_type': self.agent_type,
            'agent_id': self.agent_id,
            'channel_platform': self.channel_platform,
            'channel_chat_id': self.channel_chat_id,
            'channel_metadata': self.channel_metadata,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'message_count': self.messages.count(),
        }


class ChatMessage(db.Model):
    """Individual chat messages"""
    __tablename__ = 'chat_messages'

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.String(64), db.ForeignKey('chat_conversations.conversation_id'), nullable=False, index=True)
    role = db.Column(db.String(20), nullable=False)  # user, assistant, system, tool
    content = db.Column(db.Text, nullable=False)
    metadata_json = db.Column(db.JSON)  # tool calls, model used, tokens, thinking content

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'role': self.role,
            'content': self.content,
            'metadata': self.metadata_json or {},
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class ExternalAgent(db.Model):
    """Third-party agent registrations"""
    __tablename__ = 'external_agents'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    avatar_emoji = db.Column(db.String(10), default='🤖')
    avatar_url = db.Column(db.String(500))

    agent_type = db.Column(db.String(50), nullable=False, default='websocket')  # websocket, http_api, marketplace
    connection_url = db.Column(db.String(500))  # ws:// or https://
    auth_config = db.Column(db.JSON)  # {mode: 'pairing'|'password'|'none', token, password}
    agent_config = db.Column(db.JSON)  # {capabilities, default_model, persona}

    is_featured = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    last_connected_at = db.Column(db.DateTime)
    last_error = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', backref='external_agents')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'avatar_emoji': self.avatar_emoji,
            'avatar_url': self.avatar_url,
            'agent_type': self.agent_type,
            'connection_url': self.connection_url,
            'auth_config': {k: ('***' if k in ('token', 'password') else v) for k, v in (self.auth_config or {}).items()},
            'agent_config': self.agent_config or {},
            'is_featured': self.is_featured,
            'is_active': self.is_active,
            'last_connected_at': self.last_connected_at.isoformat() if self.last_connected_at else None,
            'last_error': self.last_error,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class WebBrowsingResult(db.Model):
    """Web browsing/research history and cache"""
    __tablename__ = 'web_browsing_results'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    conversation_id = db.Column(db.String(64), nullable=True)  # Links to chat if triggered from there

    query = db.Column(db.Text, nullable=False)
    urls_fetched = db.Column(db.JSON)  # List of URLs fetched
    extracted_content = db.Column(db.Text)  # Raw extracted text
    ai_summary = db.Column(db.Text)  # AI-generated summary

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='web_browsing_results')

    def to_dict(self):
        return {
            'id': self.id,
            'query': self.query,
            'urls_fetched': self.urls_fetched or [],
            'ai_summary': self.ai_summary,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


# ============================================
# Observability Layer Models
# ============================================

class ObsApiKey(db.Model):
    """API keys for external event ingestion, scoped to a user (workspace)."""
    __tablename__ = 'obs_api_keys'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    key_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    key_prefix = db.Column(db.String(12), nullable=False)  # e.g. "obsk_a3f1..."
    name = db.Column(db.String(100), nullable=False, default='default')
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    last_used_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='obs_api_keys')

    @staticmethod
    def hash_key(raw_key):
        return hashlib.sha256(raw_key.encode()).hexdigest()

    @classmethod
    def create_for_user(cls, user_id, name='default'):
        raw_key = f"obsk_{secrets.token_hex(24)}"
        api_key = cls(
            user_id=user_id,
            key_hash=cls.hash_key(raw_key),
            key_prefix=raw_key[:12],
            name=name,
        )
        db.session.add(api_key)
        return api_key, raw_key

    @classmethod
    def lookup(cls, raw_key):
        h = cls.hash_key(raw_key)
        return cls.query.filter_by(key_hash=h, is_active=True).first()

    def to_dict(self):
        return {
            'id': self.id,
            'key_prefix': self.key_prefix,
            'name': self.name,
            'is_active': self.is_active,
            'last_used_at': self.last_used_at.isoformat() if self.last_used_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class ObsEvent(db.Model):
    """Append-only event log for all agent observability data."""
    __tablename__ = 'obs_events'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    uid = db.Column(db.String(36), unique=True, nullable=False, index=True)  # UUID
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    agent_id = db.Column(db.Integer, db.ForeignKey('agents.id'), nullable=True)
    run_id = db.Column(db.String(36), nullable=True, index=True)
    event_type = db.Column(db.String(50), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default='info')  # success, error, info
    model = db.Column(db.String(200), nullable=True)
    tokens_in = db.Column(db.Integer, nullable=True)
    tokens_out = db.Column(db.Integer, nullable=True)
    cost_usd = db.Column(db.Numeric(12, 8), nullable=True)
    latency_ms = db.Column(db.Integer, nullable=True)
    payload = db.Column(db.JSON, nullable=False, default=dict)
    dedupe_key = db.Column(db.String(255), nullable=True, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    user = db.relationship('User', backref='obs_events')
    agent = db.relationship('Agent', backref='obs_events')

    def to_dict(self):
        return {
            'id': self.uid,
            'agent_id': self.agent_id,
            'run_id': self.run_id,
            'event_type': self.event_type,
            'status': self.status,
            'model': self.model,
            'tokens_in': self.tokens_in,
            'tokens_out': self.tokens_out,
            'cost_usd': float(self.cost_usd) if self.cost_usd else None,
            'latency_ms': self.latency_ms,
            'payload': self.payload,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class ObsRun(db.Model):
    """Tracks a single agent run (e.g. one LLM pipeline execution)."""
    __tablename__ = 'obs_runs'

    id = db.Column(db.Integer, primary_key=True)
    run_id = db.Column(db.String(36), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    agent_id = db.Column(db.Integer, db.ForeignKey('agents.id'), nullable=True)
    status = db.Column(db.String(20), default='running')  # running, success, error
    model = db.Column(db.String(200), nullable=True)
    total_tokens_in = db.Column(db.Integer, default=0)
    total_tokens_out = db.Column(db.Integer, default=0)
    total_cost_usd = db.Column(db.Numeric(12, 8), default=0)
    total_latency_ms = db.Column(db.Integer, default=0)
    tool_calls_count = db.Column(db.Integer, default=0)
    error_message = db.Column(db.Text, nullable=True)
    metadata_json = db.Column(db.JSON, default=dict)
    started_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    finished_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship('User', backref='obs_runs')
    agent = db.relationship('Agent', backref='obs_runs')

    def to_dict(self):
        return {
            'run_id': self.run_id,
            'agent_id': self.agent_id,
            'status': self.status,
            'model': self.model,
            'total_tokens_in': self.total_tokens_in,
            'total_tokens_out': self.total_tokens_out,
            'total_cost_usd': float(self.total_cost_usd) if self.total_cost_usd else 0,
            'total_latency_ms': self.total_latency_ms,
            'tool_calls_count': self.tool_calls_count,
            'error_message': self.error_message,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'finished_at': self.finished_at.isoformat() if self.finished_at else None,
        }


class ObsAgentDailyMetrics(db.Model):
    """Pre-aggregated daily metrics per agent."""
    __tablename__ = 'obs_agent_daily_metrics'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    agent_id = db.Column(db.Integer, db.ForeignKey('agents.id'), nullable=True)
    date = db.Column(db.Date, nullable=False)
    total_runs = db.Column(db.Integer, default=0)
    successful_runs = db.Column(db.Integer, default=0)
    failed_runs = db.Column(db.Integer, default=0)
    total_events = db.Column(db.Integer, default=0)
    total_tokens_in = db.Column(db.Integer, default=0)
    total_tokens_out = db.Column(db.Integer, default=0)
    total_cost_usd = db.Column(db.Numeric(12, 8), default=0)
    total_tool_calls = db.Column(db.Integer, default=0)
    tool_errors = db.Column(db.Integer, default=0)
    latency_p50_ms = db.Column(db.Integer, nullable=True)
    latency_p95_ms = db.Column(db.Integer, nullable=True)
    latency_avg_ms = db.Column(db.Integer, nullable=True)
    models_used = db.Column(db.JSON, default=dict)  # {"gpt-4o": 5, "claude-3": 3}
    last_heartbeat_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship('User', backref='obs_daily_metrics')
    agent = db.relationship('Agent', backref='obs_daily_metrics')

    __table_args__ = (db.UniqueConstraint('user_id', 'agent_id', 'date', name='_obs_daily_uc'),)

    def to_dict(self):
        total = self.total_runs or 0
        return {
            'date': self.date.isoformat() if self.date else None,
            'agent_id': self.agent_id,
            'total_runs': total,
            'successful_runs': self.successful_runs or 0,
            'failed_runs': self.failed_runs or 0,
            'success_rate': round((self.successful_runs or 0) / total, 4) if total else 0,
            'error_rate': round((self.failed_runs or 0) / total, 4) if total else 0,
            'total_tokens_in': self.total_tokens_in or 0,
            'total_tokens_out': self.total_tokens_out or 0,
            'total_cost_usd': float(self.total_cost_usd) if self.total_cost_usd else 0,
            'total_tool_calls': self.total_tool_calls or 0,
            'tool_errors': self.tool_errors or 0,
            'latency_p50_ms': self.latency_p50_ms,
            'latency_p95_ms': self.latency_p95_ms,
            'latency_avg_ms': self.latency_avg_ms,
            'models_used': self.models_used or {},
            'last_heartbeat_at': self.last_heartbeat_at.isoformat() if self.last_heartbeat_at else None,
        }


class ObsAlertRule(db.Model):
    """User-defined alert rules evaluated by cron."""
    __tablename__ = 'obs_alert_rules'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    agent_id = db.Column(db.Integer, db.ForeignKey('agents.id'), nullable=True)  # NULL = workspace-wide
    name = db.Column(db.String(100), nullable=False)
    rule_type = db.Column(db.String(50), nullable=False)  # cost_per_day, error_rate, no_heartbeat
    threshold = db.Column(db.Numeric(12, 4), nullable=False)
    window_minutes = db.Column(db.Integer, default=60)
    cooldown_minutes = db.Column(db.Integer, default=360)
    is_enabled = db.Column(db.Boolean, default=True, nullable=False)
    last_triggered_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='obs_alert_rules')
    agent = db.relationship('Agent', backref='obs_alert_rules')

    def to_dict(self):
        return {
            'id': self.id,
            'agent_id': self.agent_id,
            'name': self.name,
            'rule_type': self.rule_type,
            'threshold': float(self.threshold),
            'window_minutes': self.window_minutes,
            'cooldown_minutes': self.cooldown_minutes,
            'is_enabled': self.is_enabled,
            'last_triggered_at': self.last_triggered_at.isoformat() if self.last_triggered_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class ObsAlertEvent(db.Model):
    """Fired alerts history."""
    __tablename__ = 'obs_alert_events'

    id = db.Column(db.Integer, primary_key=True)
    rule_id = db.Column(db.Integer, db.ForeignKey('obs_alert_rules.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    agent_id = db.Column(db.Integer, db.ForeignKey('agents.id'), nullable=True)
    metric_value = db.Column(db.Numeric(12, 4), nullable=False)
    threshold_value = db.Column(db.Numeric(12, 4), nullable=False)
    rule_type = db.Column(db.String(50), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notified_slack = db.Column(db.Boolean, default=False)
    acknowledged_at = db.Column(db.DateTime, nullable=True)
    triggered_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    rule = db.relationship('ObsAlertRule', backref='alert_events')
    user = db.relationship('User', backref='obs_alert_events')

    def to_dict(self):
        return {
            'id': self.id,
            'rule_id': self.rule_id,
            'agent_id': self.agent_id,
            'rule_type': self.rule_type,
            'metric_value': float(self.metric_value),
            'threshold_value': float(self.threshold_value),
            'message': self.message,
            'notified_slack': self.notified_slack,
            'acknowledged_at': self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            'triggered_at': self.triggered_at.isoformat() if self.triggered_at else None,
        }


class ObsLlmPricing(db.Model):
    """Reference table for LLM token costs per provider/model."""
    __tablename__ = 'obs_llm_pricing'

    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(50), nullable=False)
    model = db.Column(db.String(200), nullable=False)
    input_cost_per_mtok = db.Column(db.Numeric(10, 4), nullable=False)   # USD per 1M input tokens
    output_cost_per_mtok = db.Column(db.Numeric(10, 4), nullable=False)  # USD per 1M output tokens
    effective_from = db.Column(db.Date, nullable=False)
    effective_to = db.Column(db.Date, nullable=True)  # NULL = current

    __table_args__ = (db.UniqueConstraint('provider', 'model', 'effective_from', name='_obs_pricing_uc'),)

    def to_dict(self):
        return {
            'id': self.id,
            'provider': self.provider,
            'model': self.model,
            'input_cost_per_mtok': float(self.input_cost_per_mtok),
            'output_cost_per_mtok': float(self.output_cost_per_mtok),
            'effective_from': self.effective_from.isoformat(),
            'effective_to': self.effective_to.isoformat() if self.effective_to else None,
        }


class WorkspaceTier(db.Model):
    """Observability tier configuration per workspace.

    Each workspace (currently == user) gets a row that controls feature limits.
    All enforcement reads from this table — no hard-coded limits elsewhere.
    Missing row → treated as 'free' tier via get_workspace_tier().
    """
    __tablename__ = 'workspace_tiers'

    workspace_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)
    tier_name = db.Column(db.String(50), nullable=False, default='free')  # free | production | pro | agency
    agent_limit = db.Column(db.Integer, nullable=False, default=2)
    retention_days = db.Column(db.Integer, nullable=False, default=7)
    alert_rule_limit = db.Column(db.Integer, nullable=False, default=0)
    health_history_days = db.Column(db.Integer, nullable=False, default=0)
    anomaly_detection_enabled = db.Column(db.Boolean, nullable=False, default=False)
    slack_notifications_enabled = db.Column(db.Boolean, nullable=False, default=False)
    multi_workspace_enabled = db.Column(db.Boolean, nullable=False, default=False)
    priority_processing = db.Column(db.Boolean, nullable=False, default=False)
    max_api_keys = db.Column(db.Integer, nullable=False, default=1)
    max_batch_size = db.Column(db.Integer, nullable=False, default=100)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('workspace_tier', uselist=False))

    # Canonical tier defaults — used by seed migration and get_workspace_tier() fallback.
    TIER_DEFAULTS = {
        'free': dict(
            agent_limit=2, retention_days=7, alert_rule_limit=0,
            health_history_days=0, anomaly_detection_enabled=False,
            slack_notifications_enabled=False, multi_workspace_enabled=False,
            priority_processing=False, max_api_keys=1, max_batch_size=100,
        ),
        'production': dict(
            agent_limit=10, retention_days=30, alert_rule_limit=3,
            health_history_days=7, anomaly_detection_enabled=False,
            slack_notifications_enabled=True, multi_workspace_enabled=False,
            priority_processing=False, max_api_keys=3, max_batch_size=500,
        ),
        'pro': dict(
            agent_limit=50, retention_days=90, alert_rule_limit=9999,
            health_history_days=30, anomaly_detection_enabled=True,
            slack_notifications_enabled=True, multi_workspace_enabled=False,
            priority_processing=False, max_api_keys=10, max_batch_size=1000,
        ),
        'agency': dict(
            agent_limit=9999, retention_days=180, alert_rule_limit=9999,
            health_history_days=90, anomaly_detection_enabled=True,
            slack_notifications_enabled=True, multi_workspace_enabled=True,
            priority_processing=True, max_api_keys=9999, max_batch_size=1000,
        ),
    }

    def to_dict(self):
        return {
            'workspace_id': self.workspace_id,
            'tier_name': self.tier_name,
            'agent_limit': self.agent_limit,
            'retention_days': self.retention_days,
            'alert_rule_limit': self.alert_rule_limit,
            'health_history_days': self.health_history_days,
            'anomaly_detection_enabled': self.anomaly_detection_enabled,
            'slack_notifications_enabled': self.slack_notifications_enabled,
            'multi_workspace_enabled': self.multi_workspace_enabled,
            'priority_processing': self.priority_processing,
            'max_api_keys': self.max_api_keys,
            'max_batch_size': self.max_batch_size,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class ObsAgentHealthDaily(db.Model):
    """Daily composite health score per agent (premium feature)."""
    __tablename__ = 'obs_agent_health_daily'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    agent_id = db.Column(db.Integer, db.ForeignKey('agents.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    score = db.Column(db.Numeric(5, 2), nullable=False)  # 0.00 - 100.00
    success_rate_score = db.Column(db.Numeric(5, 2), nullable=False)
    latency_score = db.Column(db.Numeric(5, 2), nullable=False)
    error_burst_score = db.Column(db.Numeric(5, 2), nullable=False)
    cost_anomaly_score = db.Column(db.Numeric(5, 2), nullable=False)
    details = db.Column(db.JSON, default=dict)  # Full breakdown
    computed_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='obs_health_scores')
    agent = db.relationship('Agent', backref='obs_health_scores')

    __table_args__ = (db.UniqueConstraint('user_id', 'agent_id', 'date', name='_obs_health_daily_uc'),)

    def to_dict(self):
        return {
            'date': self.date.isoformat() if self.date else None,
            'agent_id': self.agent_id,
            'score': float(self.score),
            'breakdown': {
                'success_rate': float(self.success_rate_score),
                'latency': float(self.latency_score),
                'error_burst': float(self.error_burst_score),
                'cost_anomaly': float(self.cost_anomaly_score),
            },
            'details': self.details or {},
            'computed_at': self.computed_at.isoformat() if self.computed_at else None,
        }
