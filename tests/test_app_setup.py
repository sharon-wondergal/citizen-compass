"""Stage 4 tests: configuration, startup safety and the database connection."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError

from app import create_app
from app.config import PLACEHOLDER_SECRET_KEY, DevelopmentConfig, ProductionConfig
from app.extensions import db
from app.logic import system

VALID_KEY = "a" * 40


def test_testing_app_uses_in_memory_database(app):
    assert app.config["TESTING"] is True
    assert app.config["SQLALCHEMY_DATABASE_URI"] == "sqlite:///:memory:"


def test_home_page_loads(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Citizen Compass is running" in response.data
    assert b"Database connection: OK" in response.data
    assert b"Foreign key checks: On" in response.data


def test_health_returns_json(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_health_reports_a_database_failure(client, monkeypatch):
    def broken_execute(*args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("secret database detail"))

    monkeypatch.setattr(system.db.session, "execute", broken_execute)
    response = client.get("/health")

    assert response.status_code == 503
    assert response.get_json() == {"status": "unavailable"}
    assert b"secret database detail" not in response.data


def test_unknown_page_returns_404(client):
    assert client.get("/no-such-page").status_code == 404


def test_foreign_keys_are_enforced(app):
    """Prove the rule works by breaking it, not only by reading the setting."""
    db.session.execute(text("CREATE TABLE parents (id INTEGER PRIMARY KEY)"))
    db.session.execute(text(
        "CREATE TABLE children (id INTEGER PRIMARY KEY, "
        "parent_id INTEGER NOT NULL REFERENCES parents(id))"
    ))
    with pytest.raises(IntegrityError):
        db.session.execute(text("INSERT INTO children (parent_id) VALUES (999)"))
    db.session.rollback()


def test_unknown_environment_is_refused():
    with pytest.raises(ValueError, match="Unknown environment"):
        create_app("staging")


@pytest.mark.parametrize("bad_key", [None, "", PLACEHOLDER_SECRET_KEY, "too-short"])
def test_weak_secret_key_stops_startup(monkeypatch, bad_key):
    monkeypatch.setattr(DevelopmentConfig, "SECRET_KEY", bad_key)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app("development")


def test_production_refuses_debug_mode(monkeypatch):
    monkeypatch.setattr(ProductionConfig, "SECRET_KEY", VALID_KEY)
    monkeypatch.setenv("FLASK_DEBUG", "1")
    with pytest.raises(RuntimeError, match="Debug mode"):
        create_app("production")


def test_production_cookie_settings(monkeypatch):
    monkeypatch.setattr(ProductionConfig, "SECRET_KEY", VALID_KEY)
    monkeypatch.setenv("FLASK_DEBUG", "0")
    production_app = create_app("production")

    assert production_app.debug is False
    assert production_app.config["SESSION_COOKIE_SECURE"] is True
    assert production_app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert production_app.config["SESSION_COOKIE_SAMESITE"] == "Lax"


def test_csrf_protection_is_on_outside_testing(monkeypatch):
    monkeypatch.setattr(DevelopmentConfig, "SECRET_KEY", VALID_KEY)
    development_app = create_app("development")

    # Flask-WTF treats a missing setting as on, so only an explicit False disables it.
    assert development_app.config.get("WTF_CSRF_ENABLED", True) is True
    assert "csrf" in development_app.extensions
