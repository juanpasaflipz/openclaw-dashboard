"""
Rate limiting configuration for OpenClaw Dashboard
"""
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os


def get_limiter_storage_uri():
    """
    Get storage URI for rate limiter
    Uses Redis in production, memory in development
    """
    redis_url = os.environ.get('REDIS_URL')
    if redis_url:
        return redis_url
    # Fallback to memory storage for development
    return "memory://"


# Initialize rate limiter
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=get_limiter_storage_uri(),
    default_limits=["1000 per hour", "100 per minute"],
    storage_options={"socket_connect_timeout": 30},
    strategy="fixed-window",  # or "moving-window" for more accurate limits
)


def init_limiter(app):
    """Initialize rate limiter with Flask app"""
    limiter.init_app(app)
    return limiter
