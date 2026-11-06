"""Checks on the health of the running application."""

from flask import current_app
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db


def check_database():
    """Report whether the database answers and foreign keys are enforced."""
    try:
        db.session.execute(text("SELECT 1"))
        if db.engine.dialect.name == "sqlite":
            foreign_keys_on = db.session.execute(text("PRAGMA foreign_keys")).scalar() == 1
        else:
            foreign_keys_on = True  # Other databases enforce them by default.
    except SQLAlchemyError:
        # Details go to the server log. Visitors never see database errors.
        current_app.logger.exception("Database check failed")
        return {"connected": False, "foreign_keys": False}

    return {"connected": True, "foreign_keys": foreign_keys_on}
