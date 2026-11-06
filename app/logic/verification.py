"""Rules for working out what verification status citizens should see."""

from datetime import date

from app.models import VerificationRecord
from app.models.base import VERIFICATION_SECTIONS

STATUS_LABELS = {
    "verified": "Verified",
    "pending": "Pending verification",
    "outdated": "Outdated – review required",
    "unavailable": "Information unavailable",
}

# Worst first. A service shows its weakest section.
STATUS_RANK = ("unavailable", "outdated", "pending", "verified")


def create_verification_records(service):
    """Give a new service one pending record for each section."""
    for section in VERIFICATION_SECTIONS:
        service.verification_records.append(VerificationRecord(section=section))


def effective_status(stored_status, review_due_on, today=None):
    """A verified record past its review date is shown as outdated."""
    today = today or date.today()
    if stored_status == "verified" and review_due_on and review_due_on < today:
        return "outdated"
    return stored_status


def section_statuses(service, today=None):
    """Return the status citizens should see for each section.

    A section with no record counts as pending, so missing information can
    never look verified. A demonstration service can never count as verified.
    """
    statuses = {section: "pending" for section in VERIFICATION_SECTIONS}
    for record in service.verification_records:
        stored = record.status
        if service.is_demo and stored == "verified":
            stored = "pending"
        statuses[record.section] = effective_status(stored, record.review_due_on, today)
    return statuses


def overall_status(service, today=None):
    """Return the weakest status across all sections of a service."""
    return min(section_statuses(service, today).values(), key=STATUS_RANK.index)
