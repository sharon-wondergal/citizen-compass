"""Citizen reports of incorrect information.

Reports are private until an administrator has checked them against official
sources. They're never published as government information.
"""

import secrets

from sqlalchemy import select

from app.extensions import db
from app.models import CitizenReport, GovernmentService

PROBLEM_LABELS = {
    "incorrect_fee": "Incorrect fee",
    "missing_document": "Missing document",
    "incorrect_office": "Incorrect office location",
    "outdated_processing": "Outdated processing time",
    "broken_link": "Broken official link",
    "other": "Other inaccurate information",
}


def open_service_choices():
    """Services citizens can see, for the report form."""
    services = db.session.scalars(
        select(GovernmentService)
        .where(GovernmentService.is_archived.is_(False))
        .order_by(GovernmentService.name)
    )
    return [(service.id, service.name) for service in services]


def find_service_id(slug):
    """Find the service a citizen came from, so the form can pre-select it."""
    return db.session.scalar(
        select(GovernmentService.id)
        .where(GovernmentService.slug == slug, GovernmentService.is_archived.is_(False))
    )


def new_reference_code():
    """A short code a citizen can quote. Random, so it reveals nothing."""
    while True:
        code = f"CC-{secrets.token_hex(3).upper()}"
        if db.session.scalar(select(CitizenReport.id).filter_by(reference_code=code)) is None:
            return code


def create_report(service_id, service_name, problem_type, description, contact_info):
    """Save a report and return its reference code."""
    service = db.session.get(GovernmentService, service_id) if service_id else None
    report = CitizenReport(
        reference_code=new_reference_code(),
        service_id=service.id if service else None,
        service_name=service.name if service else service_name,
        problem_type=problem_type,
        description=description,
        contact_info=contact_info,
    )
    db.session.add(report)
    db.session.commit()
    return report.reference_code
