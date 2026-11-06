"""Government institutions and the official sources they publish."""

from sqlalchemy import CheckConstraint

from app.extensions import db
from app.models.base import (
    INSTITUTION_TYPES,
    SOURCE_TYPES,
    VERIFICATION_STATUSES,
    LifecycleMixin,
    TimestampMixin,
    VerifiedRecordMixin,
    choice_check,
    demo_never_verified_check,
    web_link_check,
)


class GovernmentInstitution(VerifiedRecordMixin, LifecycleMixin, TimestampMixin, db.Model):
    __tablename__ = "government_institutions"
    __table_args__ = (
        choice_check("institution_type", INSTITUTION_TYPES),
        choice_check("verification_status", VERIFICATION_STATUSES),
        web_link_check("website"),
        web_link_check("source_url"),
        CheckConstraint(
            "verification_status <> 'verified' OR "
            "(source_url IS NOT NULL AND last_verified_on IS NOT NULL "
            "AND review_due_on IS NOT NULL AND verified_by_id IS NOT NULL)",
            name="verified_needs_evidence",
        ),
        demo_never_verified_check(),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, unique=True)
    slug = db.Column(db.String(220), nullable=False, unique=True)
    acronym = db.Column(db.String(20), index=True)
    institution_type = db.Column(
        db.String(20), nullable=False, default="agency", server_default="agency"
    )
    description = db.Column(db.Text)
    parent_id = db.Column(
        db.Integer,
        db.ForeignKey("government_institutions.id", ondelete="SET NULL"),
        index=True,
    )
    website = db.Column(db.String(500))
    phone = db.Column(db.String(50))
    email = db.Column(db.String(255))
    headquarters = db.Column(db.String(300))
    # A plain URL, because sources already point to institutions.
    # A link in both directions would be circular.
    source_url = db.Column(db.String(500))

    parent = db.relationship("GovernmentInstitution", remote_side=[id], back_populates="children")
    children = db.relationship("GovernmentInstitution", back_populates="parent")
    offices = db.relationship(
        "GovernmentOffice", back_populates="institution", passive_deletes="all"
    )
    services = db.relationship(
        "GovernmentService", back_populates="institution", passive_deletes="all"
    )
    sources = db.relationship(
        "OfficialSource", back_populates="institution", passive_deletes="all"
    )

    def __repr__(self):
        return f"<GovernmentInstitution {self.name}>"


class OfficialSource(TimestampMixin, db.Model):
    """One official page or document. Many services can cite the same source."""

    __tablename__ = "official_sources"
    __table_args__ = (
        choice_check("source_type", SOURCE_TYPES),
        web_link_check("url", nullable=False),
    )

    id = db.Column(db.Integer, primary_key=True)
    institution_id = db.Column(
        db.Integer,
        db.ForeignKey("government_institutions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    title = db.Column(db.String(300), nullable=False)
    url = db.Column(db.String(500), nullable=False, unique=True)
    source_type = db.Column(
        db.String(20), nullable=False, default="web_page", server_default="web_page"
    )
    published_on = db.Column(db.Date)
    last_checked_on = db.Column(db.Date)

    institution = db.relationship("GovernmentInstitution", back_populates="sources")

    def __repr__(self):
        return f"<OfficialSource {self.title}>"
