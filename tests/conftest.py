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

    # Create a temporary database for testing
    db_fd, db_path = tempfile.mkstemp(suffix='.db')

    # Configure app for testing
    flask_app.config.update({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
        'SQLALCHEMY_TRACK_MODIFICATIONS': False,
        'SECRET_KEY': 'test-secret-key',
        'WTF_CSRF_ENABLED': False,  # Disable CSRF for testing
        'STRIPE_SECRET_KEY': 'sk_test_fake_key',
        'STRIPE_WEBHOOK_SECRET': 'whsec_test_fake_secret',
        'SENDGRID_API_KEY': 'test_sendgrid_key',
    })

    # Create tables
    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()

    # Close and remove temporary database
    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture(scope='function')
def client(app):
    """Create a test client for the Flask application"""
    return app.test_client()


@pytest.fixture(scope='function')
def db_session(app):
    """Create a new database session for each test"""
    from models import db

    with app.app_context():
        # Begin a nested transaction
        connection = db.engine.connect()
        transaction = connection.begin()

        # Bind the session to the connection
        db.session.bind = connection

        yield db.session

        # Rollback the transaction after the test
        transaction.rollback()
        connection.close()
        db.session.remove()


@pytest.fixture
def user(app, db_session):
    """Create a test user"""
    from models import User

    user = User(
        email='test@example.com',
        created_at=datetime.utcnow(),
        credit_balance=10,
        subscription_tier='free',
        subscription_status='inactive'
    )
    db_session.add(user)
    db_session.commit()

    return user


@pytest.fixture
def premium_user(app, db_session):
    """Create a premium test user"""
    from models import User

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
    db_session.add(user)
    db_session.commit()

    return user


@pytest.fixture
def admin_user(app, db_session):
    """Create an admin test user"""
    from models import User

    user = User(
        email='admin@example.com',
        created_at=datetime.utcnow(),
        credit_balance=1000,
        subscription_tier='pro',
        subscription_status='active',
        is_admin=True
    )
    db_session.add(user)
    db_session.commit()

    return user


@pytest.fixture
def magic_link(app, db_session, user):
    """Create a valid magic link for testing"""
    from models import MagicLink
    import secrets

    token = secrets.token_urlsafe(32)
    magic_link = MagicLink(
        user_id=user.id,
        token=token,
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(hours=1),
        used=False
    )
    db_session.add(magic_link)
    db_session.commit()

    return magic_link


@pytest.fixture
def expired_magic_link(app, db_session, user):
    """Create an expired magic link for testing"""
    from models import MagicLink
    import secrets

    token = secrets.token_urlsafe(32)
    magic_link = MagicLink(
        user_id=user.id,
        token=token,
        created_at=datetime.utcnow() - timedelta(hours=2),
        expires_at=datetime.utcnow() - timedelta(hours=1),
        used=False
    )
    db_session.add(magic_link)
    db_session.commit()

    return magic_link


@pytest.fixture
def authenticated_client(client, user, app):
    """Create a test client with an authenticated session"""
    with client.session_transaction() as sess:
        sess['user_id'] = user.id
        sess['user_email'] = user.email

    return client


@pytest.fixture
def agent(app, db_session, user):
    """Create a test agent"""
    from models import Agent

    agent = Agent(
        user_id=user.id,
        name='TestAgent',
        moltbook_username='testagent',
        moltbook_api_key='test_api_key',
        is_primary=True,
        created_at=datetime.utcnow()
    )
    db_session.add(agent)
    db_session.commit()

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
