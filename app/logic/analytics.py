"""Privacy-friendly usage counts."""

from datetime import date

from flask import current_app
from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import DailyView


def add_view(today, **record):
    """Add one to today's total for a service or an institution.

    Only the daily total is stored, never who viewed the page. A problem here
    must not stop a citizen from seeing the page.
    """
    today = today or date.today()
    try:
        updated = db.session.execute(
            update(DailyView)
            .filter_by(view_date=today, **record)
            .values(view_count=DailyView.view_count + 1)
        ).rowcount
        if not updated:
            db.session.add(DailyView(view_date=today, view_count=1, **record))
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Could not record a page view")


def record_service_view(service_id, today=None):
    add_view(today, service_id=service_id)


def record_institution_view(institution_id, today=None):
    add_view(today, institution_id=institution_id)
