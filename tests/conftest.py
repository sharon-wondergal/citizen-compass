"""Shared test setup. Pytest finds this file automatically."""

from datetime import date

import pytest

from app import create_app
from app.extensions import db
from app.models import (
    AdminUser,
    District,
    GovernmentInstitution,
    GovernmentOffice,
    GovernmentService,
    OfficialSource,
    Region,
    ServiceCategory,
)


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


@pytest.fixture
def database(app):
    """Temporary tables, removed after each test."""
    db.create_all()
    yield db
    db.session.remove()
    db.drop_all()


class SampleData:
    """Invented records for tests. None of this is real government information."""

    def __init__(self):
        self.today = date(2026, 1, 1)
        self.review_date = date(2026, 7, 1)

        self.region = Region(name="Example Region")
        self.district = District(name="Example District", region=self.region)
        self.editor = AdminUser(
            full_name="Example Editor", email="editor@example.test", password_hash="x"
        )
        self.verifier = AdminUser(
            full_name="Example Verifier",
            email="verifier@example.test",
            password_hash="x",
            role="verifier",
        )
        self.institution = GovernmentInstitution(
            name="Example Agency", slug="example-agency", is_demo=True
        )
        self.source = OfficialSource(
            institution=self.institution,
            title="Example Source",
            url="https://example.test/source",
        )
        self.category = ServiceCategory(name="Example Category", slug="example-category")
        self.office = GovernmentOffice(
            institution=self.institution,
            district=self.district,
            name="Example Office",
            is_demo=True,
        )
        self.service = GovernmentService(
            institution=self.institution,
            category=self.category,
            name="Example Service",
            slug="example-service",
            summary="Example only",
            is_demo=True,
        )


@pytest.fixture
def sample(database):
    data = SampleData()
    database.session.add_all(
        [data.region, data.editor, data.verifier, data.institution, data.category]
    )
    database.session.commit()
    return data
