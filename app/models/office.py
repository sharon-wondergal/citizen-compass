"""Government offices, and which services each office provides."""

from sqlalchemy import CheckConstraint, UniqueConstraint

from app.extensions import db
from app.models.base import (
    OFFICE_TYPES,
    VERIFICATION_STATUSES,
    LifecycleMixin,
    TimestampMixin,
    VerifiedRecordMixin,
    choice_check,
    demo_never_verified_check,
    status_column,
    web_link_check,
)


class GovernmentOffice(VerifiedRecordMixin, LifecycleMixin, TimestampMixin, db.Model):
    __tablename__ = "government_offices"
    __table_args__ = (
        UniqueConstraint("institution_id", "name"),
        choice_check("office_type", OFFICE_TYPES),
        choice_check("verification_status", VERIFICATION_STATUSES),
        web_link_check("website"),
        CheckConstraint(
            "latitude IS NULL OR latitude BETWEEN -90 AND 90", name="latitude_range"
        ),
        CheckConstraint(
            "longitude IS NULL OR longitude BETWEEN -180 AND 180", name="longitude_range"
        ),
        CheckConstraint(
            "(latitude IS NULL) = (longitude IS NULL)", name="coordinates_together"
        ),
        CheckConstraint(
            "verification_status <> 'verified' OR "
            "(source_id IS NOT NULL AND last_verified_on IS NOT NULL "
            "AND review_due_on IS NOT NULL AND verified_by_id IS NOT NULL)",
            name="verified_needs_evidence",
        ),
        demo_never_verified_check(),
    )

    id = db.Column(db.Integer, primary_key=True)
    institution_id = db.Column(
        db.Integer,
        db.ForeignKey("government_institutions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    district_id = db.Column(
        db.Integer, db.ForeignKey("districts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    source_id = db.Column(db.Integer, db.ForeignKey("official_sources.id", ondelete="RESTRICT"))
    name = db.Column(db.String(200), nullable=False)
    office_type = db.Column(
        db.String(20), nullable=False, default="district", server_default="district"
    )
    physical_address = db.Column(db.String(300))  # Empty until confirmed.
    phone = db.Column(db.String(50))
    email = db.Column(db.String(255))
    website = db.Column(db.String(500))
    opening_hours = db.Column(db.String(200))
    latitude = db.Column(db.Float)  # Map-ready. Empty until confirmed.
    longitude = db.Column(db.Float)

    institution = db.relationship("GovernmentInstitution", back_populates="offices")
    district = db.relationship("District", back_populates="offices")
    source = db.relationship("OfficialSource")
    service_links = db.relationship(
        "ServiceOffice",
        back_populates="office",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self):
        return f"<GovernmentOffice {self.name}>"


class ServiceOffice(db.Model):
    """The claim that an office provides a service. It needs its own evidence."""

    __tablename__ = "service_offices"
    __table_args__ = (
        UniqueConstraint("service_id", "office_id"),
        choice_check("verification_status", VERIFICATION_STATUSES),
        CheckConstraint(
            "verification_status <> 'verified' OR "
            "(source_id IS NOT NULL AND last_verified_on IS NOT NULL)",
            name="verified_needs_evidence",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    service_id = db.Column(
        db.Integer, db.ForeignKey("government_services.id", ondelete="CASCADE"), nullable=False
    )
    office_id = db.Column(
        db.Integer,
        db.ForeignKey("government_offices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_id = db.Column(db.Integer, db.ForeignKey("official_sources.id", ondelete="RESTRICT"))
    availability_note = db.Column(db.String(300))
    verification_status = status_column()
    last_verified_on = db.Column(db.Date)

    service = db.relationship("GovernmentService", back_populates="office_links")
    office = db.relationship("GovernmentOffice", back_populates="service_links")
    source = db.relationship("OfficialSource")

    def __repr__(self):
        return f"<ServiceOffice service={self.service_id} office={self.office_id}>"
