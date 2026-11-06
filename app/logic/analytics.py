"""Privacy-friendly usage counts."""

from datetime import date

from flask import current_app
from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import DailyView


def record_service_view(service_id, today=None):
    """Add one to today's total for a service.

    Only the daily total is stored, never who viewed the page. A problem here
    must not stop a citizen from seeing their checklist.
    """
    today = today or date.today()
    try:
        updated = db.session.execute(
            update(DailyView)
            .where(DailyView.view_date == today, DailyView.service_id == service_id)
            .values(view_count=DailyView.view_count + 1)
        ).rowcount
        if not updated:
            db.session.add(DailyView(view_date=today, service_id=service_id, view_count=1))
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Could not record a service view")
