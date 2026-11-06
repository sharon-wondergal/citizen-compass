"""Proves the models and the migration match the design tested in Stage 2."""

import sqlite3
from pathlib import Path

import pytest
from flask_migrate import upgrade

from app import create_app
from app.config import TestingConfig
from app.extensions import db
from tests.schema_compare import describe_database

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DESIGN_FILE = PROJECT_ROOT / "docs" / "schema_prototype.sql"
MIGRATIONS_FOLDER = PROJECT_ROOT / "migrations"


@pytest.fixture
def design():
    """The structure of the Stage 2 design, built from its SQL file."""
    connection = sqlite3.connect(":memory:")
    connection.executescript(DESIGN_FILE.read_text(encoding="utf-8"))
    description = describe_database(connection)
    connection.close()
    return description


def assert_same_structure(actual, design):
    assert sorted(actual) == sorted(design)
    for table in design:
        for part in design[table]:
            assert actual[table][part] == design[table][part], f"{table}: {part} differs"


def test_design_has_19_tables(design):
    assert len(design) == 19


def test_models_match_the_design(database, design):
    connection = database.engine.raw_connection()
    try:
        actual = describe_database(connection)
    finally:
        connection.close()
    assert_same_structure(actual, design)


def test_migration_builds_the_designed_database(tmp_path, monkeypatch, design):
    """Run the real migration on an empty file, as a new computer would."""
    database_file = tmp_path / "migration_test.db"
    monkeypatch.setattr(
        TestingConfig, "SQLALCHEMY_DATABASE_URI", f"sqlite:///{database_file.as_posix()}"
    )
    migrated_app = create_app("testing")

    with migrated_app.app_context():
        upgrade(directory=str(MIGRATIONS_FOLDER))
        db.session.remove()
        db.engine.dispose()

    connection = sqlite3.connect(database_file)
    try:
        actual = describe_database(connection)
    finally:
        connection.close()
    assert_same_structure(actual, design)
