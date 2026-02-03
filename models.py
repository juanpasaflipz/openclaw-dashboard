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

    # Credits for Moltbook posting
    credit_balance = db.Column(db.Integer, default=0)

    # Stripe integration
    stripe_customer_id = db.Column(db.String(255), unique=True, index=True)

    # Relationships
    transactions = db.relationship('CreditTransaction', backref='user', lazy='dynamic')
    magic_links = db.relationship('MagicLink', backref='user', lazy='dynamic')
    post_history = db.relationship('PostHistory', backref='user', lazy='dynamic')

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
