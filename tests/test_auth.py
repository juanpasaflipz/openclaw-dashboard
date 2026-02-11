"""
Tests for magic link authentication system
"""
import pytest
from datetime import datetime, timedelta
from models import User, MagicLink, db


@pytest.mark.auth
class TestMagicLinkRequest:
    """Tests for requesting magic links"""

    def test_request_magic_link_new_user(self, client, app):
        """Test requesting magic link creates new user"""
        response = client.post('/api/auth/request-magic-link', json={
            'email': 'newuser@example.com'
        })

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'Magic link sent' in data['message']

        # Verify user was created
        user = User.query.filter_by(email='newuser@example.com').first()
        assert user is not None
        assert user.credit_balance == 5  # Free credits for new users

        # Verify magic link was created
        magic_link = MagicLink.query.filter_by(user_id=user.id).first()
        assert magic_link is not None
        assert magic_link.is_valid()

    def test_request_magic_link_existing_user(self, client, user, app):
        """Test requesting magic link for existing user"""
        response = client.post('/api/auth/request-magic-link', json={
            'email': user.email
        })

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True

        # Verify no duplicate user was created
        users = User.query.filter_by(email='test@example.com').all()
        assert len(users) == 1

        # Verify new magic link was created
        magic_link = MagicLink.query.filter_by(user_id=user.id).first()
        assert magic_link is not None

    def test_request_magic_link_missing_email(self, client):
        """Test requesting magic link without email"""
        response = client.post('/api/auth/request-magic-link', json={})

        assert response.status_code == 400
        data = response.get_json()
        assert 'Email is required' in data['error']

    def test_request_magic_link_invalid_email(self, client):
        """Test requesting magic link with invalid email"""
        response = client.post('/api/auth/request-magic-link', json={
            'email': 'notanemail'
        })

        assert response.status_code == 400
        data = response.get_json()
        assert 'Invalid email address' in data['error']

    def test_request_magic_link_email_normalization(self, client, app):
        """Test that emails are normalized (lowercase, trimmed)"""
        response = client.post('/api/auth/request-magic-link', json={
            'email': '  TestUser@EXAMPLE.COM  '
        })

        assert response.status_code == 200

        # Verify email was normalized
        user = User.query.filter_by(email='testuser@example.com').first()
        assert user is not None

    def test_request_magic_link_owner_becomes_admin(self, client, app, monkeypatch):
        """Test that owner email gets admin privileges"""
        monkeypatch.setenv('OWNER_EMAIL', 'owner@example.com')

        response = client.post('/api/auth/request-magic-link', json={
            'email': 'owner@example.com'
        })

        assert response.status_code == 200

        user = User.query.filter_by(email='owner@example.com').first()
        assert user is not None
        assert user.is_admin is True


@pytest.mark.auth
class TestMagicLinkVerification:
    """Tests for verifying magic links"""

    def test_verify_valid_magic_link(self, client, magic_link, user, app):
        """Test verifying a valid magic link"""
        token = magic_link.token
        ml_id = magic_link.id
        user_id = user.id

        response = client.get(f'/api/auth/verify?token={token}')

        assert response.status_code == 200
        assert b'Login Successful' in response.data

        # Re-query from DB (scoped session is removed after request)
        ml = MagicLink.query.get(ml_id)
        assert ml.used_at is not None

        u = User.query.get(user_id)
        assert u.last_login is not None

    def test_verify_magic_link_creates_session(self, client, magic_link, user, app):
        """Test that verification creates a user session"""
        token = magic_link.token
        client.get(f'/api/auth/verify?token={token}')

        # Verify session was created by checking /api/auth/me
        response = client.get('/api/auth/me')
        assert response.status_code == 200
        data = response.get_json()
        assert data['authenticated'] is True
        assert data['user']['email'] == 'test@example.com'

    def test_verify_expired_magic_link(self, client, expired_magic_link):
        """Test verifying an expired magic link"""
        response = client.get(f'/api/auth/verify?token={expired_magic_link.token}')

        assert response.status_code == 400
        data = response.get_json()
        assert 'expired' in data['error'].lower()

    def test_verify_used_magic_link(self, client, magic_link, app):
        """Test verifying a magic link that was already used"""
        ml_id = magic_link.id

        # Use the magic link once
        magic_link.mark_as_used()
        db.session.commit()

        # Re-query to get a fresh instance after the commit
        ml = MagicLink.query.get(ml_id)
        token = ml.token

        # Try to use it again
        response = client.get(f'/api/auth/verify?token={token}')

        assert response.status_code == 400
        data = response.get_json()
        assert 'already used' in data['error'].lower() or 'expired' in data['error'].lower()

    def test_verify_invalid_token(self, client):
        """Test verifying with invalid token"""
        response = client.get('/api/auth/verify?token=invalid_token_xyz')

        assert response.status_code == 404
        data = response.get_json()
        assert 'Invalid magic link' in data['error']

    def test_verify_missing_token(self, client):
        """Test verifying without token"""
        response = client.get('/api/auth/verify')

        assert response.status_code == 400
        data = response.get_json()
        assert 'Token is required' in data['error']


@pytest.mark.auth
class TestAuthenticationState:
    """Tests for authentication state management"""

    def test_get_current_user_authenticated(self, authenticated_client, user):
        """Test getting current user info when authenticated"""
        response = authenticated_client.get('/api/auth/me')

        assert response.status_code == 200
        data = response.get_json()
        assert data['authenticated'] is True
        assert data['user']['id'] == user.id
        assert data['user']['email'] == user.email
        assert data['user']['credit_balance'] == user.credit_balance
        assert data['user']['subscription_tier'] == user.subscription_tier
        assert data['user']['is_admin'] == user.is_admin

    def test_get_current_user_unauthenticated(self, client):
        """Test getting current user info when not authenticated"""
        response = client.get('/api/auth/me')

        assert response.status_code == 401
        data = response.get_json()
        assert data['authenticated'] is False

    def test_logout(self, authenticated_client):
        """Test logging out"""
        # Verify we're authenticated
        response = authenticated_client.get('/api/auth/me')
        assert response.status_code == 200

        # Logout
        response = authenticated_client.post('/api/auth/logout')
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True

        # Verify we're no longer authenticated
        response = authenticated_client.get('/api/auth/me')
        assert response.status_code == 401


@pytest.mark.auth
@pytest.mark.unit
class TestMagicLinkModel:
    """Unit tests for MagicLink model"""

    def test_generate_token(self):
        """Test token generation"""
        token1 = MagicLink.generate_token()
        token2 = MagicLink.generate_token()

        assert len(token1) > 20  # Should be reasonably long
        assert token1 != token2  # Should be unique

    def test_create_for_user(self, app, user):
        """Test creating magic link for user"""
        magic_link = MagicLink.create_for_user(user.id, expires_in_minutes=30)
        db.session.commit()

        assert magic_link.user_id == user.id
        assert magic_link.token is not None
        assert magic_link.expires_at > datetime.utcnow()
        assert magic_link.is_valid()

    def test_is_valid_new_link(self, app, user):
        """Test that new magic link is valid"""
        magic_link = MagicLink.create_for_user(user.id)
        db.session.commit()

        assert magic_link.is_valid() is True

    def test_is_valid_expired_link(self, app, user):
        """Test that expired magic link is invalid"""
        magic_link = MagicLink(
            user_id=user.id,
            token='test_token_expired',
            created_at=datetime.utcnow() - timedelta(hours=2),
            expires_at=datetime.utcnow() - timedelta(hours=1)
        )
        db.session.add(magic_link)
        db.session.commit()

        assert magic_link.is_valid() is False

    def test_is_valid_used_link(self, app, user):
        """Test that used magic link is invalid"""
        magic_link = MagicLink.create_for_user(user.id)
        magic_link.mark_as_used()
        db.session.commit()

        assert magic_link.is_valid() is False

    def test_mark_as_used(self, app, user):
        """Test marking magic link as used"""
        magic_link = MagicLink.create_for_user(user.id)
        db.session.commit()

        assert magic_link.used_at is None

        magic_link.mark_as_used()
        db.session.commit()

        assert magic_link.used_at is not None
        assert isinstance(magic_link.used_at, datetime)
