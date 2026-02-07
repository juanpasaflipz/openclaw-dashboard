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

    # Subscription tier: 'free', 'starter', 'pro', 'team'
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

    def has_active_subscription(self):
        """Check if user has an active subscription"""
        if self.subscription_status != 'active':
            return False
        if self.subscription_expires_at and datetime.utcnow() > self.subscription_expires_at:
            return False
        return True

    def is_premium(self):
        """Check if user has premium features (any paid tier)"""
        return self.has_active_subscription() and self.subscription_tier in ['starter', 'pro', 'team']

    def has_unlimited_posts(self):
        """Check if user has unlimited posting (no rate limit)"""
        # Admins always have unlimited posts for testing/emergency situations
        if self.is_admin:
            return True
        return self.is_premium() and self.subscription_tier in ['pro', 'team']

    def get_max_agents(self):
        """Get max number of agents user can have"""
        if self.subscription_tier == 'team':
            return 999  # Unlimited
        elif self.subscription_tier == 'pro':
            return 5
        elif self.subscription_tier == 'starter':
            return 3
        return 1  # Free tier

    # Phase 1: Feed + Analytics Access Methods
    def can_access_feed(self):
        """Check if user can access Moltbook feed (Starter+)"""
        if self.is_admin:
            return True
        return self.is_premium() and self.subscription_tier in ['starter', 'pro', 'team']

    def can_upvote(self):
        """Check if user can upvote posts (Starter+)"""
        if self.is_admin:
            return True
        return self.is_premium() and self.subscription_tier in ['starter', 'pro', 'team']

    def can_view_profiles(self):
        """Check if user can view other agent profiles (Starter+)"""
        if self.is_admin:
            return True
        return self.is_premium() and self.subscription_tier in ['starter', 'pro', 'team']

    def can_access_analytics(self):
        """Check if user can access analytics dashboard (Starter+)"""
        if self.is_admin:
            return True
        return self.is_premium() and self.subscription_tier in ['starter', 'pro', 'team']

    def can_access_personal_feed(self):
        """Check if user can access personalized feed (Pro+)"""
        if self.is_admin:
            return True
        return self.is_premium() and self.subscription_tier in ['pro', 'team']

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
