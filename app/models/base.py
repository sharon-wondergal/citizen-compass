"""Shared building blocks for the database models.

The allowed values live here once, so forms, pages and the database rules can
all use the same lists.
"""

from sqlalchemy import CheckConstraint, text
from sqlalchemy.orm import declared_attr

from app.extensions import db

# ---------- Allowed values ----------

VERIFICATION_STATUSES = ("pending", "verified", "outdated", "unavailable")
ADMIN_ROLES = ("editor", "verifier", "super_admin")
INSTITUTION_TYPES = ("ministry", "department", "agency", "local_government", "other")
SOURCE_TYPES = ("web_page", "pdf", "client_charter", "gazette", "other")
OFFICE_TYPES = ("headquarters", "regional", "district", "service_centre", "other")
DELIVERY_MODES = ("online", "physical", "hybrid")
FEE_KINDS = ("official", "other_charge")
SERVICE_SPEEDS = ("ordinary", "express", "not_applicable")
PROCESSING_STARTS = ("submission", "payment", "approval", "unknown")
PROCESSING_BASES = ("official_standard", "estimate", "unverified")
STEP_STAGES = ("before_visit", "at_office", "after_visit")
VERIFICATION_SECTIONS = ("overview", "documents", "fees", "offices", "processing")
PROBLEM_TYPES = (
    "incorrect_fee",
    "missing_document",
    "incorrect_office",
    "outdated_processing",
    "broken_link",
    "other",
)
REPORT_STATUSES = ("new", "investigating", "resolved", "dismissed")
AUDIT_ACTIONS = (
    "create",
    "update",
    "delete",
    "archive",
    "restore",
    "verify",
    "status_change",
    "resolve_report",
    "login",
)


# ---------- Rule helpers ----------

def choice_check(column, choices, nullable=False):
    """Database rule: the column must hold one of the allowed values."""
    quoted = ", ".join(f"'{choice}'" for choice in choices)
    rule = f"{column} IN ({quoted})"
    if nullable:
        rule = f"{column} IS NULL OR {rule}"
    return CheckConstraint(rule, name=f"{column}_valid")


def web_link_check(column, nullable=True):
    """Database rule: links must be http or https, which blocks javascript: links."""
    rule = f"{column} LIKE 'http://%' OR {column} LIKE 'https://%'"
    if nullable:
        rule = f"{column} IS NULL OR {rule}"
    return CheckConstraint(rule, name=f"{column}_is_web_link")


def minimum_check(column, minimum, nullable=True):
    """Database rule: the number can't be below the minimum."""
    rule = f"{column} >= {minimum}"
    if nullable:
        rule = f"{column} IS NULL OR {rule}"
    return CheckConstraint(rule, name=f"{column}_minimum")


def flag(default):
    """A required yes/no column with a default."""
    return db.Column(
        db.Boolean,
        nullable=False,
        default=default,
        server_default=text("1" if default else "0"),
    )


def order_column():
    """A display position, for sorting items on a page."""
    return db.Column(db.Integer, nullable=False, default=0, server_default=text("0"))


def status_column():
    """A verification status. Everything starts as pending."""
    return db.Column(db.String(20), nullable=False, default="pending", server_default="pending")


# ---------- Mixins: columns shared by several tables ----------

class TimestampMixin:
    created_at = db.Column(
        db.DateTime, nullable=False, server_default=db.func.current_timestamp()
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )


class LifecycleMixin:
    """Demonstration records are labelled. Archived records are hidden, not deleted."""

    is_demo = flag(False)
    is_archived = flag(False)


class VerifiedRecordMixin:
    """Verification details for institutions and offices."""

    verification_status = status_column()
    last_verified_on = db.Column(db.Date)
    review_due_on = db.Column(db.Date)

    @declared_attr
    def verified_by_id(cls):
        return db.Column(db.Integer, db.ForeignKey("admin_users.id", ondelete="RESTRICT"))

    @declared_attr
    def verified_by(cls):
        return db.relationship("AdminUser", foreign_keys=[cls.verified_by_id])


def demo_never_verified_check():
    """Database rule: invented records can't be presented as verified."""
    return CheckConstraint(
        "NOT (is_demo = 1 AND verification_status = 'verified')",
        name="demo_never_verified",
    )
