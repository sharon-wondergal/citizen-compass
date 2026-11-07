"""The verification workflow: checking information against official sources.

The database already refuses "verified" without evidence. This module adds the
rules a database can't check by itself:

* Nobody can verify their own work.
* Demonstration records can never be verified.
* A section must contain real content before it can be verified.

Each review saves its audit entry in the same commit as the change.
"""

import json
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, selectinload

from app.extensions import db
from app.logic.audit import record_audit
from app.logic.checklist import describe_duration
from app.logic.records import differences, reset_section, snapshot
from app.logic.search import RESULTS_PER_PAGE, SearchResults
from app.logic.verification import STATUS_LABELS, effective_status
from app.models import (
    AuditLog,
    GovernmentInstitution,
    GovernmentOffice,
    GovernmentService,
    OfficialSource,
    ServiceOffice,
)
from app.template_helpers import ugx

REVIEW_PERIOD_DAYS = 180
DUE_SOON_DAYS = 30

OWN_WORK_MESSAGE = "You made the last change here, so a different person must verify it."
DEMO_MESSAGE = "Demonstration records can never be verified."


class ReviewRefused(Exception):
    """A review broke a rule. The message explains why."""


def default_review_date(checked_on):
    return checked_on + timedelta(days=REVIEW_PERIOD_DAYS)


def last_editor_id(table_name, record_id):
    """Who last created or changed a record, according to the audit trail.

    Institutions, offices and office links have no "last edited by" column.
    """
    return db.session.scalar(
        select(AuditLog.admin_user_id)
        .where(
            AuditLog.table_name == table_name,
            AuditLog.record_id == record_id,
            AuditLog.action.in_(("create", "update")),
        )
        .order_by(AuditLog.id.desc())
        .limit(1)
    )


def open_links(service):
    return [link for link in service.office_links if not link.office.is_archived]


def section_problems(service, section):
    """Reasons a section can't be verified yet, as plain sentences."""
    problems = []
    if section == "overview":
        if not service.eligibility:
            problems.append("Who qualifies hasn't been filled in.")
        if not service.delivery_mode:
            problems.append("How the service is provided hasn't been filled in.")
    elif section == "documents" and not service.documents:
        problems.append("No documents have been added.")
    elif section == "fees" and not service.fees:
        problems.append("No fees have been added. If it's free, add a fee of 0.")
    elif section == "processing" and not service.processing:
        problems.append("No processing time has been added.")
    elif section == "offices":
        links = open_links(service)
        if not links:
            problems.append("No offices have been linked.")
        if any(link.verification_status != "verified" for link in links):
            problems.append("Every linked office must be verified first.")
    return problems


def section_summary(service, section):
    """What a verifier needs to compare with the source, including hidden fees."""
    if section == "overview":
        return [
            f"Summary: {service.summary}",
            f"Who qualifies: {service.eligibility or 'Not confirmed'}",
            f"How it's provided: {service.delivery_mode or 'Not confirmed'}",
            f"Official portal: {service.online_url or 'None'}",
        ] + [f"Step {step.step_number}: {step.title}" for step in service.steps]
    if section == "documents":
        return [
            f"{item.name} ({'required' if item.is_mandatory else 'optional'})"
            + (f", {item.variant.name}" if item.variant else "")
            for item in service.documents
        ]
    if section == "fees":
        return [
            f"{item.fee_name}: "
            + ("Amount not confirmed" if item.amount_ugx is None else ugx(item.amount_ugx))
            for item in service.fees
        ]
    if section == "processing":
        return [
            f"{describe_duration(item)}" + (f" ({item.duration_note})" if item.duration_note else "")
            for item in service.processing
        ]
    return [
        f"{link.office.name}: {STATUS_LABELS[link.verification_status]}"
        for link in open_links(service)
    ]


def save_review(record, before, admin, status, label):
    """Save a review with its audit entry, or explain why it was refused."""
    old, new = differences(before, snapshot(record))
    record_audit(
        admin,
        "verify" if status == "verified" else "status_change",
        record.__tablename__,
        record.id,
        label,
        old,
        new,
    )
    try:
        db.session.commit()
    except IntegrityError as error:
        db.session.rollback()
        raise ReviewRefused("That review couldn't be saved. Check the details.") from error


def mark_source_checked(source_id, checked_on):
    source = db.session.get(OfficialSource, source_id)
    if source is not None:
        source.last_checked_on = checked_on


def review_section(record, admin, status, source_id, checked_on, review_due_on, notes):
    service = record.service
    if status == "verified":
        if service.is_demo:
            raise ReviewRefused(DEMO_MESSAGE)
        if record.last_edited_by_id == admin.id:
            raise ReviewRefused(OWN_WORK_MESSAGE)
        problems = section_problems(service, record.section)
        if problems:
            raise ReviewRefused(" ".join(problems))
        mark_source_checked(source_id, checked_on)

    before = snapshot(record)
    record.status = status
    record.source_id = source_id
    record.last_checked_on = checked_on
    record.notes = notes
    record.verified_by_id = admin.id if status == "verified" else None
    record.review_due_on = review_due_on if status == "verified" else None
    save_review(record, before, admin, status, f"{service.name}: {record.section}")


def review_directory_record(record, admin, status, checked_on, review_due_on, evidence):
    """Review an institution or office. Evidence is its source_url or source_id."""
    if status == "verified":
        if record.is_demo:
            raise ReviewRefused(DEMO_MESSAGE)
        if last_editor_id(record.__tablename__, record.id) == admin.id:
            raise ReviewRefused(OWN_WORK_MESSAGE)

    before = snapshot(record)
    for name, value in evidence.items():
        setattr(record, name, value)
    record.verification_status = status
    record.last_verified_on = checked_on
    record.verified_by_id = admin.id if status == "verified" else None
    record.review_due_on = review_due_on if status == "verified" else None
    save_review(record, before, admin, status, record.name)


def review_office_link(link, admin, status, source_id, checked_on):
    service = link.service
    if status == "verified":
        if service.is_demo or link.office.is_demo:
            raise ReviewRefused(DEMO_MESSAGE)
        if last_editor_id("service_offices", link.id) == admin.id:
            raise ReviewRefused(OWN_WORK_MESSAGE)
        mark_source_checked(source_id, checked_on)
    else:
        # A link that's no longer confirmed can't sit under a verified section.
        reset_section(service, "offices", admin)

    before = snapshot(link)
    link.verification_status = status
    link.source_id = source_id
    link.last_verified_on = checked_on
    save_review(link, before, admin, status, f"{service.name}: {link.office.name}")


# ---------- The review queue ----------

def queue_item(kind, name, url_values, status, due_on=None):
    return {
        "kind": kind,
        "name": name,
        "target": url_values,
        "status": status,
        "label": STATUS_LABELS[status],
        "due_on": due_on,
    }


def add_to_queue(queue, item, stored_status, due_on, today):
    """Sort one item into overdue, waiting or due soon. Others need no action."""
    status = item["status"]
    if status == "outdated":
        queue["overdue"].append(item)
    elif status in ("pending", "unavailable"):
        queue["waiting"].append(item)
    elif stored_status == "verified" and due_on <= today + timedelta(days=DUE_SOON_DAYS):
        queue["due_soon"].append(item)


def build_queue(today=None):
    """Everything needing a verifier's attention.

    Demonstration and archived records are left out, because they need no check.
    """
    today = today or date.today()
    queue = {"overdue": [], "waiting": [], "due_soon": []}

    services = db.session.scalars(
        select(GovernmentService)
        .where(GovernmentService.is_archived.is_(False), GovernmentService.is_demo.is_(False))
        .options(
            selectinload(GovernmentService.verification_records),
            selectinload(GovernmentService.office_links).joinedload(ServiceOffice.office),
        )
        .order_by(GovernmentService.name)
    ).unique().all()

    for service in services:
        for record in service.verification_records:
            status = effective_status(record.status, record.review_due_on, today)
            item = queue_item(
                record.section.capitalize(), service.name,
                ("admin.review_service_section", {"service_id": service.id, "section": record.section}),
                status, record.review_due_on,
            )
            add_to_queue(queue, item, record.status, record.review_due_on, today)

        for link in open_links(service):
            if link.verification_status != "verified":
                queue["waiting"].append(queue_item(
                    "Office link", f"{service.name}: {link.office.name}",
                    ("admin.review_link", {"service_id": service.id, "link_id": link.id}),
                    link.verification_status,
                ))

    for model, kind_name, kind in (
        (GovernmentInstitution, "institutions", "Institution"),
        (GovernmentOffice, "offices", "Office"),
    ):
        records = db.session.scalars(
            select(model)
            .where(model.is_archived.is_(False), model.is_demo.is_(False))
            .order_by(model.name)
        )
        for record in records:
            status = effective_status(record.verification_status, record.review_due_on, today)
            item = queue_item(
                kind, record.name,
                ("admin.review_record", {"kind_name": kind_name, "record_id": record.id}),
                status, record.review_due_on,
            )
            add_to_queue(queue, item, record.verification_status, record.review_due_on, today)

    return queue


# ---------- Update history ----------

def describe_changes(old_values, new_values):
    """Turn an audit entry's saved values into readable lines."""
    old = json.loads(old_values) if old_values else {}
    new = json.loads(new_values) if new_values else {}
    return [
        {
            "field": field.replace("_", " ").capitalize(),
            "old": "empty" if old.get(field) is None else old[field],
            "new": "empty" if new.get(field) is None else new[field],
        }
        for field in sorted(set(old) | set(new))
    ]


def audit_page(page, action=""):
    """One page of the audit trail, newest first."""
    conditions = [AuditLog.action == action] if action else []
    total = db.session.scalar(select(func.count()).select_from(AuditLog).where(*conditions))
    pages = max(-(-total // RESULTS_PER_PAGE), 1)
    page = min(page, pages)

    entries = db.session.scalars(
        select(AuditLog)
        .where(*conditions)
        .options(joinedload(AuditLog.admin_user))
        .order_by(AuditLog.id.desc())
        .offset((page - 1) * RESULTS_PER_PAGE)
        .limit(RESULTS_PER_PAGE)
    ).all()

    items = [
        {"entry": entry, "changes": describe_changes(entry.old_values, entry.new_values)}
        for entry in entries
    ]
    return SearchResults(items=items, total=total, page=page, pages=pages)
