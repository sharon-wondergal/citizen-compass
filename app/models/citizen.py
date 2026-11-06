"""Citizen reports and privacy-friendly usage statistics.

No table here stores an IP address or identifies a visitor.
"""

from sqlalchemy import CheckConstraint, UniqueConstraint, text

from app.extensions import db
from app.models.base import PROBLEM_TYPES, REPORT_STATUSES, choice_check, minimum_check


class CitizenReport(db.Model):
    __tablename__ = "citizen_reports"
    __table_args__ = (
        choice_check("problem_type", PROBLEM_TYPES),
        choice_check("status", REPORT_STATUSES),
        CheckConstraint("length(description) BETWEEN 10 AND 2000", name="description_length"),
        CheckConstraint(
            "status NOT IN ('resolved', 'dismissed') OR "
            "(action_taken IS NOT NULL AND resolved_by_id IS NOT NULL "
            "AND resolved_at IS NOT NULL)",
            name="closed_needs_action",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    reference_code = db.Column(db.String(20), nullable=False, unique=True)
    service_id = db.Column(
        db.Integer, db.ForeignKey("government_services.id", ondelete="SET NULL")
    )
    service_name = db.Column(db.String(200), nullable=False)
    problem_type = db.Column(db.String(30), nullable=False)
    description = db.Column(db.String(2000), nullable=False)
    contact_info = db.Column(db.String(200))  # Optional.
    status = db.Column(
        db.String(20), nullable=False, default="new", server_default="new", index=True
    )
    action_taken = db.Column(db.Text)
    resolved_by_id = db.Column(db.Integer, db.ForeignKey("admin_users.id", ondelete="RESTRICT"))
    resolved_at = db.Column(db.DateTime)
    submitted_at = db.Column(
        db.DateTime, nullable=False, server_default=db.func.current_timestamp()
    )

    service = db.relationship("GovernmentService", back_populates="reports")
    resolved_by = db.relationship("AdminUser")

    def __repr__(self):
        return f"<CitizenReport {self.reference_code}>"


class SearchLog(db.Model):
    __tablename__ = "search_logs"
    __table_args__ = (minimum_check("results_count", 0, nullable=False),)

    id = db.Column(db.Integer, primary_key=True)
    query_text = db.Column(db.String(100), nullable=False)
    results_count = db.Column(db.Integer, nullable=False)
    top_service_id = db.Column(
        db.Integer, db.ForeignKey("government_services.id", ondelete="SET NULL")
    )
    top_institution_id = db.Column(
        db.Integer, db.ForeignKey("government_institutions.id", ondelete="SET NULL")
    )
    searched_at = db.Column(
        db.DateTime, nullable=False, server_default=db.func.current_timestamp(), index=True
    )

    def __repr__(self):
        return f"<SearchLog {self.query_text}>"


class DailyView(db.Model):
    """Daily totals only. Individual visits are never recorded."""

    __tablename__ = "daily_views"
    __table_args__ = (
        UniqueConstraint("view_date", "service_id"),
        UniqueConstraint("view_date", "institution_id"),
        minimum_check("view_count", 0, nullable=False),
        # Each row counts exactly one thing.
        CheckConstraint(
            "(service_id IS NULL) <> (institution_id IS NULL)", name="counts_one_thing"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    view_date = db.Column(db.Date, nullable=False)
    service_id = db.Column(
        db.Integer, db.ForeignKey("government_services.id", ondelete="CASCADE")
    )
    institution_id = db.Column(
        db.Integer, db.ForeignKey("government_institutions.id", ondelete="CASCADE")
    )
    view_count = db.Column(db.Integer, nullable=False, default=0, server_default=text("0"))

    def __repr__(self):
        return f"<DailyView {self.view_date}: {self.view_count}>"
