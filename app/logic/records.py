"""Rules for changing records from the admin area.

Two rules matter most:

1. Changing verified information makes it pending again. Otherwise a fee could
   change while still showing "Verified".
2. Every change is saved together with its audit entry, showing old and new values.
"""

import re

from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.logic.audit import record_audit
from app.models import GovernmentOffice, ServiceOffice, VerificationRecord

# These columns are never copied into the audit trail.
NOT_AUDITED = {"id", "created_at", "updated_at", "password_hash"}

# Form fields that aren't part of the record.
NOT_RECORD_FIELDS = {"csrf_token", "submit"}


def snapshot(record):
    """Return the record's current values, for comparing before and after."""
    return {
        column.key: getattr(record, column.key)
        for column in inspect(record).mapper.column_attrs
        if column.key not in NOT_AUDITED
    }


def differences(before, after):
    """Return only the values that changed, as (old, new)."""
    changed = [key for key in after if before.get(key) != after[key]]
    return (
        {key: before.get(key) for key in changed},
        {key: after[key] for key in changed},
    )


def apply_form(form, record):
    """Copy form values onto a record. Field names match the column names."""
    for field in form:
        if field.name not in NOT_RECORD_FIELDS:
            setattr(record, field.name, field.data)


def make_slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:200] or "record"


def unique_slug(model, text):
    """Make a web address part that no other record uses.

    Slugs aren't changed when a record is renamed, so shared links keep working.
    """
    base = make_slug(text)
    slug = base
    number = 2
    while db.session.scalar(select(model.id).filter_by(slug=slug)) is not None:
        slug = f"{base}-{number}"
        number += 1
    return slug


def reset_section(service, section, admin):
    """Send one section of a service back to pending, naming who changed it."""
    record = next(
        (item for item in service.verification_records if item.section == section), None
    )
    if record is None:
        record = VerificationRecord(section=section)
        service.verification_records.append(record)
    record.status = "pending"
    record.verified_by = None
    record.last_checked_on = None
    record.review_due_on = None
    record.last_edited_by = admin


def reset_record(record):
    """Send an institution or office back to pending."""
    record.verification_status = "pending"
    record.verified_by = None
    record.last_verified_on = None
    record.review_due_on = None


def reset_office(office, admin):
    """A changed office affects the checklists of every service it offers."""
    reset_record(office)
    for link in office.service_links:
        link.verification_status = "pending"
        link.last_verified_on = None
        reset_section(link.service, "offices", admin)


def reset_records_citing(source, admin):
    """A source moved to a new address, so whatever relied on it needs rechecking."""
    records = db.session.scalars(
        select(VerificationRecord).filter_by(source_id=source.id)
    ).all()
    for record in records:
        reset_section(record.service, record.section, admin)

    for link in db.session.scalars(select(ServiceOffice).filter_by(source_id=source.id)):
        link.verification_status = "pending"
        link.last_verified_on = None
        reset_section(link.service, "offices", admin)

    for office in db.session.scalars(select(GovernmentOffice).filter_by(source_id=source.id)):
        reset_office(office, admin)


def save_change(record, before, admin, on_change=None):
    """Save a new or edited record with its audit entry.

    on_change(old, new) runs only if something really changed. It's where
    verification gets reset, so saving an unchanged form resets nothing.
    Returns False if the database refused the change, such as a duplicate name.
    """
    creating = inspect(record).transient
    try:
        db.session.add(record)
        db.session.flush()
        old, new = differences(before, snapshot(record))
        if old or new or creating:
            if on_change:
                on_change(old, new)
            record_audit(
                admin,
                "create" if creating else "update",
                record.__tablename__,
                record.id,
                audit_label(record),
                None if creating else old,
                new,
            )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return False
    return True


def delete_record(record, admin, on_change=None):
    """Delete a record with its audit entry.

    Returns False if other records still depend on it.
    """
    old = snapshot(record)
    record_id = record.id
    table_name = record.__tablename__
    label = audit_label(record)
    try:
        db.session.delete(record)
        db.session.flush()
        if on_change:
            on_change()
        record_audit(admin, "delete", table_name, record_id, label, old)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return False
    return True


def set_archived(record, archived, admin):
    """Hide or restore a record. Archived records stay in the database."""
    record.is_archived = archived
    record_audit(
        admin,
        "archive" if archived else "restore",
        record.__tablename__,
        record.id,
        audit_label(record),
    )
    db.session.commit()


def audit_label(record):
    """A readable name for the audit trail."""
    for attribute in ("name", "fee_name", "title"):
        value = getattr(record, attribute, None)
        if value:
            return str(value)[:200]
    return f"{record.__tablename__} {record.id}"
