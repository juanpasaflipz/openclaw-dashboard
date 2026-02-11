"""
Pytest configuration and shared fixtures for OpenClaw Dashboard tests
"""
import pytest
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set test environment before importing app
os.environ['FLASK_ENV'] = 'testing'
os.environ['TESTING'] = 'true'


@pytest.fixture(scope='session')
def app():
    """Create and configure a test Flask application instance"""
    from server import app as flask_app
    from models import db
    from rate_limiter import limiter

    # Create a temporary database for testing
    db_fd, db_path = tempfile.mkstemp(suffix='.db')

    # Configure app for testing
    flask_app.config.update({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
        'SQLALCHEMY_TRACK_MODIFICATIONS': False,
        'SECRET_KEY': 'test-secret-key',
        'WTF_CSRF_ENABLED': False,
        'STRIPE_SECRET_KEY': 'sk_test_fake_key',
        'STRIPE_WEBHOOK_SECRET': 'whsec_test_fake_secret',
        'SENDGRID_API_KEY': 'test_sendgrid_key',
    })

    # Disable rate limiting for tests (must be done after init_limiter ran)
    limiter.enabled = False

    # Create tables inside a persistent app context
    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()

    # Close and remove temporary database
    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture(autouse=True)
def _clean_db(app):
    """Clean up data between tests to avoid UNIQUE constraint violations."""
    from models import db
    yield
    db.session.rollback()
    for table in reversed(db.metadata.sorted_tables):
        db.session.execute(table.delete())
    db.session.commit()


@pytest.fixture(scope='function')
def client(app):
    """Create a test client for the Flask application"""
    return app.test_client()


@pytest.fixture
def user(app):
    """Create a test user"""
    from models import User, db

    user = User(
        email='test@example.com',
        created_at=datetime.utcnow(),
        credit_balance=10,
        subscription_tier='free',
        subscription_status='inactive'
    )
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def premium_user(app):
    """Create a premium test user"""
    from models import User, db

    user = User(
        email='premium@example.com',
        created_at=datetime.utcnow(),
        credit_balance=100,
        subscription_tier='pro',
        subscription_status='active',
        stripe_customer_id='cus_test_premium',
        stripe_subscription_id='sub_test_premium',
        subscription_expires_at=datetime.utcnow() + timedelta(days=30),
        subscription_started_at=datetime.utcnow()
    )
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def admin_user(app):
    """Create an admin test user"""
    from models import User, db

    user = User(
        email='admin@example.com',
        created_at=datetime.utcnow(),
        credit_balance=1000,
        subscription_tier='pro',
        subscription_status='active',
        is_admin=True
    )
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def magic_link(app, user):
    """Create a valid magic link for testing"""
    from models import MagicLink, db
    import secrets

    token = secrets.token_urlsafe(32)
    ml = MagicLink(
        user_id=user.id,
        token=token,
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(hours=1),
    )
    db.session.add(ml)
    db.session.commit()
    return ml


@pytest.fixture
def expired_magic_link(app, user):
    """Create an expired magic link for testing"""
    from models import MagicLink, db
    import secrets

    token = secrets.token_urlsafe(32)
    ml = MagicLink(
        user_id=user.id,
        token=token,
        created_at=datetime.utcnow() - timedelta(hours=2),
        expires_at=datetime.utcnow() - timedelta(hours=1),
    )
    db.session.add(ml)
    db.session.commit()
    return ml


@pytest.fixture
def authenticated_client(client, user, app):
    """Create a test client with an authenticated session"""
    with client.session_transaction() as sess:
        sess['user_id'] = user.id
        sess['user_email'] = user.email
    return client


@pytest.fixture
def agent(app, user):
    """Create a test agent"""
    from models import Agent, db

    agent = Agent(
        user_id=user.id,
        name='TestAgent',
        description='A test agent',
        is_active=True,
        is_default=True,
        created_at=datetime.utcnow()
    )
    db.session.add(agent)
    db.session.commit()
    return agent


@pytest.fixture
def mock_stripe_event():
    """Create a mock Stripe event for webhook testing"""
    def _create_event(event_type, data):
        return {
            'id': 'evt_test_123',
            'object': 'event',
            'type': event_type,
            'data': {
                'object': data
            },
            'created': int(datetime.utcnow().timestamp())
        }
    return _create_event


@pytest.fixture
def mock_stripe_subscription():
    """Create a mock Stripe subscription object"""
    return {
        'id': 'sub_test_123',
        'customer': 'cus_test_123',
        'status': 'active',
        'items': {
            'data': [{
                'price': {
                    'id': 'price_test_starter'
                }
            }]
        },
        'current_period_end': int((datetime.utcnow() + timedelta(days=30)).timestamp()),
        'current_period_start': int(datetime.utcnow().timestamp())
    }


@pytest.fixture
def mock_stripe_customer():
    """Create a mock Stripe customer object"""
    return {
        'id': 'cus_test_123',
        'email': 'test@example.com',
        'metadata': {}
    }
