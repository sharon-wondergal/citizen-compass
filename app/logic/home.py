"""Collects the information shown on the homepage."""

from datetime import date, timedelta

from sqlalchemy import and_, func, select

from app.extensions import db
from app.models import DailyView, GovernmentInstitution, GovernmentService, ServiceCategory

POPULAR_SERVICE_LIMIT = 6
POPULAR_PERIOD_DAYS = 30
INSTITUTION_LIMIT = 8


def popular_services(today=None):
    """The most viewed services over the last 30 days.

    "Popular" comes only from real view counts, so with no visits this is empty.
    """
    today = today or date.today()
    since = today - timedelta(days=POPULAR_PERIOD_DAYS)
    statement = (
        select(GovernmentService)
        .join(DailyView, DailyView.service_id == GovernmentService.id)
        .where(GovernmentService.is_archived.is_(False), DailyView.view_date >= since)
        .group_by(GovernmentService.id)
        .order_by(func.sum(DailyView.view_count).desc(), GovernmentService.name)
        .limit(POPULAR_SERVICE_LIMIT)
    )
    return db.session.scalars(statement).all()


def categories_with_counts():
    """Active categories, each with its number of available services."""
    statement = (
        select(ServiceCategory, func.count(GovernmentService.id))
        .outerjoin(
            GovernmentService,
            and_(
                GovernmentService.category_id == ServiceCategory.id,
                GovernmentService.is_archived.is_(False),
            ),
        )
        .where(ServiceCategory.is_active.is_(True))
        .group_by(ServiceCategory.id)
        .order_by(ServiceCategory.display_order, ServiceCategory.name)
    )
    return db.session.execute(statement).all()


def institutions_with_counts():
    """Institutions offering the most available services."""
    statement = (
        select(GovernmentInstitution, func.count(GovernmentService.id))
        .outerjoin(
            GovernmentService,
            and_(
                GovernmentService.institution_id == GovernmentInstitution.id,
                GovernmentService.is_archived.is_(False),
            ),
        )
        .where(GovernmentInstitution.is_archived.is_(False))
        .group_by(GovernmentInstitution.id)
        .order_by(func.count(GovernmentService.id).desc(), GovernmentInstitution.name)
        .limit(INSTITUTION_LIMIT)
    )
    return db.session.execute(statement).all()
