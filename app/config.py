"""Application settings.

Each environment is a class. Development, testing and production share the
base settings in Config and change only what must differ.

Secrets come from environment variables, never from this file.
"""

import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Read .env into the environment before the classes below use it.
# Real environment variables win, which is what a live server needs.
load_dotenv(PROJECT_ROOT / ".env")

PLACEHOLDER_SECRET_KEY = "replace-with-a-long-random-value"
MINIMUM_SECRET_KEY_LENGTH = 32


class Config:
    """Settings shared by every environment."""

    ENV_NAME = "base"

    SECRET_KEY = os.environ.get("SECRET_KEY")

    # Flask-SQLAlchemy stores a relative SQLite path in the instance folder.
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///citizen_compass.db")

    # Session cookies: JavaScript can't read them, and other sites can't send them.
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=2)

    # Refuse oversized requests. Citizen reports are short text.
    MAX_CONTENT_LENGTH = 1024 * 1024

    # Rate limit counts are kept in memory. Stage 15 reviews this for live use.
    RATELIMIT_STORAGE_URI = "memory://"


class DevelopmentConfig(Config):
    ENV_NAME = "development"


class TestingConfig(Config):
    ENV_NAME = "testing"
    TESTING = True

    # Each test gets a fresh database in memory, so real data is never touched.
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SECRET_KEY = "testing-only-key-never-used-on-a-real-server"

    # Tests post forms directly and repeat requests quickly.
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False


class ProductionConfig(Config):
    ENV_NAME = "production"

    # Send the session cookie over HTTPS only.
    SESSION_COOKIE_SECURE = True


CONFIGS = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(config_name=None):
    """Return the settings class, using APP_ENV if no name is given."""
    name = config_name or os.environ.get("APP_ENV", "development")
    if name not in CONFIGS:
        allowed = ", ".join(CONFIGS)
        raise ValueError(f"Unknown environment '{name}'. Use one of: {allowed}.")
    return CONFIGS[name]


def validate_config(app):
    """Stop the app from starting with unsafe settings.

    Failing loudly at startup is better than running with a weak secret.
    """
    secret_key = app.config.get("SECRET_KEY")
    if not secret_key or secret_key == PLACEHOLDER_SECRET_KEY:
        raise RuntimeError("SECRET_KEY is not set. Create one and add it to .env (see README).")
    if len(secret_key) < MINIMUM_SECRET_KEY_LENGTH:
        raise RuntimeError(f"SECRET_KEY must be at least {MINIMUM_SECRET_KEY_LENGTH} characters.")

    if app.config["ENV_NAME"] == "production" and app.debug:
        raise RuntimeError("Debug mode must be off in production. Set FLASK_DEBUG=0.")
