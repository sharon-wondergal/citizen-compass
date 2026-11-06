"""Collects the numbers shown on the administrator dashboard."""

from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload, selectinload

from app.extensions import db
from app.logic.verification import STATUS_LABELS, overall_status
from app.models import (
    CitizenReport,
    GovernmentInstitution,
    GovernmentOffice,
    GovernmentService,
)

RECENT_LIMIT = 6
OPEN_REPORT_STATUSES = ("new", "investigating")


def count_open(model):
    return db.session.scalar(
        select(func.count()).select_from(model).where(model.is_archived.is_(False))
    )


def bar_rows(counts):
    """Turn {label: count} into rows for a bar chart, largest first.

    Each bar's width is its share of the largest count.
    """
    largest = max(counts.values(), default=0)
    rows = [
        {
            "label": label,
            "count": count,
            "percent": round(count / largest * 100) if largest else 0,
        }
        for label, count in counts.items()
    ]
    return sorted(rows, key=lambda row: (-row["count"], row["label"]))


def recently_updated():
    """The latest changes across services, institutions and offices."""
    kinds = (
        (GovernmentService, "Service"),
        (GovernmentInstitution, "Institution"),
        (GovernmentOffice, "Office"),
    )
    records = []
    for model, kind in kinds:
        rows = db.session.scalars(
            select(model)
            .where(model.is_archived.is_(False))
            .order_by(model.updated_at.desc())
            .limit(RECENT_LIMIT)
        )
        records.extend({"kind": kind, "name": row.name, "updated_at": row.updated_at} for row in rows)
    records.sort(key=lambda record: record["updated_at"], reverse=True)
    return records[:RECENT_LIMIT]


def build_dashboard(today=None):
    services = db.session.scalars(
        select(GovernmentService)
        .where(GovernmentService.is_archived.is_(False))
        .options(
            joinedload(GovernmentService.category),
            selectinload(GovernmentService.verification_records),
        )
    ).all()

    statuses = Counter(overall_status(service, today) for service in services)
    categories = Counter(service.category.name for service in services)

    status_rows = [
        {
            "status": status,
            "label": label,
            "count": statuses[status],
            "percent": round(statuses[status] / len(services) * 100) if services else 0,
        }
        for status, label in STATUS_LABELS.items()
    ]

    return {
        "total_services": len(services),
        "total_institutions": count_open(GovernmentInstitution),
        "total_offices": count_open(GovernmentOffice),
        "verified_services": statuses["verified"],
        "pending_services": statuses["pending"],
        "outdated_services": statuses["outdated"],
        "open_reports": db.session.scalar(
            select(func.count())
            .select_from(CitizenReport)
            .where(CitizenReport.status.in_(OPEN_REPORT_STATUSES))
        ),
        "status_rows": status_rows,
        "category_rows": bar_rows(categories),
        "recent": recently_updated(),
    }
