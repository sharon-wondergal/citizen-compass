"""One verification record per section of each service.

This is the heart of the trust model: fees can be verified while processing
time is still pending, and citizens can see the difference.
"""

from sqlalchemy import CheckConstraint, Index, UniqueConstraint

from app.extensions import db
from app.models.base import (
    VERIFICATION_SECTIONS,
    VERIFICATION_STATUSES,
    choice_check,
    status_column,
)


class VerificationRecord(db.Model):
    __tablename__ = "verification_records"
    __table_args__ = (
        UniqueConstraint("service_id", "section"),
        choice_check("section", VERIFICATION_SECTIONS),
        choice_check("status", VERIFICATION_STATUSES),
        CheckConstraint(
            "status <> 'verified' OR "
            "(source_id IS NOT NULL AND last_checked_on IS NOT NULL "
            "AND review_due_on IS NOT NULL AND verified_by_id IS NOT NULL)",
            name="verified_needs_evidence",
        ),
        # Separate approval: the last editor can't verify their own change.
        CheckConstraint(
            "status <> 'verified' OR last_edited_by_id IS NULL "
            "OR verified_by_id <> last_edited_by_id",
            name="separate_approval",
        ),
        Index("ix_verification_records_status_review", "status", "review_due_on"),
    )

    id = db.Column(db.Integer, primary_key=True)
    service_id = db.Column(
        db.Integer, db.ForeignKey("government_services.id", ondelete="CASCADE"), nullable=False
    )
    section = db.Column(db.String(20), nullable=False)
    status = status_column()
    source_id = db.Column(db.Integer, db.ForeignKey("official_sources.id", ondelete="RESTRICT"))
    last_checked_on = db.Column(db.Date)
    review_due_on = db.Column(db.Date)
    verified_by_id = db.Column(db.Integer, db.ForeignKey("admin_users.id", ondelete="RESTRICT"))
    last_edited_by_id = db.Column(db.Integer, db.ForeignKey("admin_users.id", ondelete="RESTRICT"))
    notes = db.Column(db.Text)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )

    service = db.relationship("GovernmentService", back_populates="verification_records")
    source = db.relationship("OfficialSource")
    verified_by = db.relationship("AdminUser", foreign_keys=[verified_by_id])
    last_edited_by = db.relationship("AdminUser", foreign_keys=[last_edited_by_id])

    def __repr__(self):
        return f"<VerificationRecord {self.section}: {self.status}>"
