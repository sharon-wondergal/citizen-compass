"""Collects the information shown on the homepage."""

from datetime import date, timedelta

from sqlalchemy import and_, func, select

from app.extensions import db
from app.models import (
    DailyView,
    GovernmentInstitution,
    GovernmentOffice,
    GovernmentService,
    ServiceCategory,
)

POPULAR_SERVICE_LIMIT = 6
MINIMUM_POPULAR_SERVICES = 3
QUICK_TAG_LIMIT = 7
POPULAR_PERIOD_DAYS = 30
INSTITUTION_LIMIT = 8


def site_counts():
    """How much the directory holds, counting only records citizens can see."""

    def count_open(model):
        return db.session.scalar(
            select(func.count()).select_from(model).where(model.is_archived.is_(False))
        )

    return {
        "services": count_open(GovernmentService),
        "institutions": count_open(GovernmentInstitution),
        "offices": count_open(GovernmentOffice),
        "demo_services": db.session.scalar(
            select(func.count())
            .select_from(GovernmentService)
            .where(GovernmentService.is_archived.is_(False), GovernmentService.is_demo.is_(True))
        ),
    }


def popular_services(today=None):
    """The most viewed services over the last 30 days.

    "Popular" comes only from recorded view counts, so with no views this is empty.
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


def featured_services():
    """Services for the homepage, and an honest heading for them.

    "Popular" is only claimed when real views exist. Otherwise the same space
    lists the services that are available.
    """
    popular = popular_services()
    if len(popular) >= MINIMUM_POPULAR_SERVICES:
        return "Popular services", "The services people have viewed most in the last 30 days.", popular

    services = db.session.scalars(
        select(GovernmentService)
        .where(GovernmentService.is_archived.is_(False))
        .order_by(GovernmentService.name)
        .limit(POPULAR_SERVICE_LIMIT)
    ).all()
    return "Available services", "Open a service to see its preparation checklist.", services


def quick_tags():
    """Shortcut buttons under the search box. Real services come before fictional ones."""
    services = db.session.scalars(
        select(GovernmentService)
        .where(GovernmentService.is_archived.is_(False))
        .order_by(GovernmentService.is_demo, GovernmentService.name)
        .limit(QUICK_TAG_LIMIT)
    ).all()
    return [
        {
            "label": service.name.removeprefix("Demonstration "),
            "query": service.name,
            "slug": service.slug,
            "is_demo": service.is_demo,
        }
        for service in services
    ]


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
