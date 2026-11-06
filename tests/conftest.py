"""Shared test setup. Pytest finds this file automatically."""

import pytest

from app import create_app


@pytest.fixture
def app():
    """A fresh application with a temporary in-memory database."""
    test_app = create_app("testing")
    with test_app.app_context():
        yield test_app


@pytest.fixture
def client(app):
    """A pretend browser that sends requests to the app."""
    return app.test_client()
