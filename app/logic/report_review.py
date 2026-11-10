"""Reviewing citizen reports, and removing personal details that are no longer needed.

Reports never change public information by themselves. An administrator checks
the official source, edits the service if needed, and records what was done.
"""

from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.logic.audit import record_audit
from app.logic.auth import utc_now
from app.logic.records import differences, snapshot
from app.logic.search import paginate
from app.models import CitizenReport, SearchLog

OPEN_STATUSES = ("new", "investigating")
CLOSED_STATUSES = ("resolved", "dismissed")
REPORT_STATUS_LABELS = {
    "new": "New",
    "investigating": "Investigating",
    "resolved": "Resolved",
    "dismissed": "Dismissed",
}

# The retention periods proposed in the Stage 2 design document.
CONTACT_KEPT_DAYS = 90
SEARCH_LOG_KEPT_DAYS = 365


def list_reports(status_filter, page):
    """Reports, newest first. "open" means new or under investigation."""
    statement = (
        select(CitizenReport)
        .options(joinedload(CitizenReport.service))
        .order_by(CitizenReport.submitted_at.desc(), CitizenReport.id.desc())
    )
    if status_filter == "open":
        statement = statement.where(CitizenReport.status.in_(OPEN_STATUSES))
    elif status_filter in REPORT_STATUS_LABELS:
        statement = statement.where(CitizenReport.status == status_filter)
    return paginate(db.session.scalars(statement).all(), page)


def update_report(report, admin, status, action_taken, now=None):
    """Record a decision on a report, with its audit entry."""
    before = snapshot(report)
    report.status = status
    report.action_taken = action_taken

    if status in CLOSED_STATUSES:
        report.resolved_by_id = admin.id
        report.resolved_at = now or utc_now()
    else:
        report.resolved_by_id = None
        report.resolved_at = None

    old, new = differences(before, snapshot(report))
    if old or new:
        record_audit(
            admin,
            "resolve_report" if status in CLOSED_STATUSES else "status_change",
            "citizen_reports",
            report.id,
            report.reference_code,
            old,
            new,
        )
    db.session.commit()


def remove_old_personal_data(now=None):
    """Blank old contact details and delete old searches.

    Returns how many contacts were blanked and how many searches were deleted.
    """
    now = now or utc_now()
    contact_cutoff = now - timedelta(days=CONTACT_KEPT_DAYS)
    search_cutoff = now - timedelta(days=SEARCH_LOG_KEPT_DAYS)

    reports = db.session.scalars(
        select(CitizenReport).where(
            CitizenReport.status.in_(CLOSED_STATUSES),
            CitizenReport.resolved_at < contact_cutoff,
            CitizenReport.contact_info.is_not(None),
        )
    ).all()
    for report in reports:
        report.contact_info = None

    deleted = db.session.execute(
        delete(SearchLog).where(SearchLog.searched_at < search_cutoff)
    ).rowcount
    db.session.commit()
    return len(reports), deleted


def count_open_reports():
    return db.session.scalar(
        select(func.count())
        .select_from(CitizenReport)
        .where(CitizenReport.status.in_(OPEN_STATUSES))
    )
