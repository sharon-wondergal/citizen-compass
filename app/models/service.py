"""Government services and the details shown on the preparation checklist.

In the detail tables, variant_id empty means "applies to every variant".
"""

from sqlalchemy import CheckConstraint, UniqueConstraint

from app.extensions import db
from app.models.base import (
    DELIVERY_MODES,
    FEE_KINDS,
    PROCESSING_BASES,
    PROCESSING_STARTS,
    SERVICE_SPEEDS,
    STEP_STAGES,
    LifecycleMixin,
    TimestampMixin,
    choice_check,
    flag,
    minimum_check,
    order_column,
    web_link_check,
)


def service_link():
    return db.Column(
        db.Integer,
        db.ForeignKey("government_services.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


def variant_link():
    return db.Column(db.Integer, db.ForeignKey("service_variants.id", ondelete="CASCADE"))


def source_link():
    return db.Column(db.Integer, db.ForeignKey("official_sources.id", ondelete="RESTRICT"))


def speed_column():
    return db.Column(
        db.String(20), nullable=False, default="not_applicable", server_default="not_applicable"
    )


def child_of_service(model_name, order_by=None):
    """A list of rows that belong to a service and are deleted with it."""
    return db.relationship(
        model_name,
        back_populates="service",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by=order_by,
    )


class ServiceCategory(db.Model):
    __tablename__ = "service_categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    slug = db.Column(db.String(140), nullable=False, unique=True)
    description = db.Column(db.Text)
    icon = db.Column(db.String(50))
    display_order = order_column()
    is_active = flag(True)

    services = db.relationship(
        "GovernmentService", back_populates="category", passive_deletes="all"
    )

    def __repr__(self):
        return f"<ServiceCategory {self.name}>"


class GovernmentService(LifecycleMixin, TimestampMixin, db.Model):
    __tablename__ = "government_services"
    __table_args__ = (
        UniqueConstraint("institution_id", "name"),
        choice_check("delivery_mode", DELIVERY_MODES, nullable=True),
        web_link_check("online_url"),
    )

    id = db.Column(db.Integer, primary_key=True)
    institution_id = db.Column(
        db.Integer,
        db.ForeignKey("government_institutions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    category_id = db.Column(
        db.Integer,
        db.ForeignKey("service_categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(220), nullable=False, unique=True)
    summary = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text)
    eligibility = db.Column(db.Text)
    delivery_mode = db.Column(db.String(10))  # Empty until confirmed.
    online_url = db.Column(db.String(500))
    keywords = db.Column(db.String(500))  # Everyday search words and other names.
    created_by_id = db.Column(db.Integer, db.ForeignKey("admin_users.id", ondelete="RESTRICT"))

    institution = db.relationship("GovernmentInstitution", back_populates="services")
    category = db.relationship("ServiceCategory", back_populates="services")
    created_by = db.relationship("AdminUser")

    variants = child_of_service("ServiceVariant", "ServiceVariant.display_order")
    documents = child_of_service("RequiredDocument", "RequiredDocument.display_order")
    fees = child_of_service("ServiceFee", "ServiceFee.display_order")
    processing = child_of_service("ProcessingInformation")
    steps = child_of_service("ServiceStep", "ServiceStep.step_number")
    verification_records = child_of_service("VerificationRecord")
    office_links = child_of_service("ServiceOffice")

    # Reports are kept if a service is removed, so these rows are not deleted with it.
    reports = db.relationship("CitizenReport", back_populates="service", passive_deletes=True)

    def __repr__(self):
        return f"<GovernmentService {self.name}>"


class ServiceVariant(db.Model):
    """The citizen's situation, such as new, renewal or lost.

    Ordinary and express are not variants. They are the service_speed column.
    """

    __tablename__ = "service_variants"
    __table_args__ = (UniqueConstraint("service_id", "name"),)

    id = db.Column(db.Integer, primary_key=True)
    service_id = db.Column(
        db.Integer, db.ForeignKey("government_services.id", ondelete="CASCADE"), nullable=False
    )
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text)
    is_default = flag(False)
    display_order = order_column()

    service = db.relationship("GovernmentService", back_populates="variants")

    def __repr__(self):
        return f"<ServiceVariant {self.name}>"


class RequiredDocument(db.Model):
    """In the yes/no and number columns, empty means "not yet confirmed"."""

    __tablename__ = "required_documents"
    __table_args__ = (
        minimum_check("photocopies", 0),
        minimum_check("max_age_days", 1),
    )

    id = db.Column(db.Integer, primary_key=True)
    service_id = service_link()
    variant_id = variant_link()
    source_id = source_link()
    name = db.Column(db.String(200), nullable=False)
    is_mandatory = flag(True)
    original_required = db.Column(db.Boolean)
    photocopies = db.Column(db.Integer)
    certified_copy_accepted = db.Column(db.Boolean)
    max_age_days = db.Column(db.Integer)
    instructions = db.Column(db.Text)
    display_order = order_column()

    service = db.relationship("GovernmentService", back_populates="documents")
    variant = db.relationship("ServiceVariant")
    source = db.relationship("OfficialSource")

    def __repr__(self):
        return f"<RequiredDocument {self.name}>"


class ServiceFee(db.Model):
    __tablename__ = "service_fees"
    __table_args__ = (
        choice_check("fee_kind", FEE_KINDS),
        choice_check("service_speed", SERVICE_SPEEDS),
        minimum_check("amount_ugx", 0),
    )

    id = db.Column(db.Integer, primary_key=True)
    service_id = service_link()
    variant_id = variant_link()
    source_id = source_link()
    fee_name = db.Column(db.String(200), nullable=False)
    fee_kind = db.Column(
        db.String(20), nullable=False, default="official", server_default="official"
    )
    service_speed = speed_column()
    # Whole shillings. Empty means not confirmed. 0 means confirmed free.
    amount_ugx = db.Column(db.Integer)
    is_mandatory = flag(True)
    payment_method = db.Column(db.String(200))
    payment_instructions = db.Column(db.Text)
    effective_from = db.Column(db.Date)
    display_order = order_column()

    service = db.relationship("GovernmentService", back_populates="fees")
    variant = db.relationship("ServiceVariant")
    source = db.relationship("OfficialSource")

    def __repr__(self):
        return f"<ServiceFee {self.fee_name}>"


class ProcessingInformation(db.Model):
    __tablename__ = "processing_information"
    __table_args__ = (
        choice_check("service_speed", SERVICE_SPEEDS),
        choice_check("starts_after", PROCESSING_STARTS),
        choice_check("basis", PROCESSING_BASES),
        minimum_check("min_working_days", 0),
        minimum_check("max_working_days", 0),
        CheckConstraint(
            "min_working_days IS NULL OR max_working_days IS NULL "
            "OR min_working_days <= max_working_days",
            name="days_in_order",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    service_id = service_link()
    variant_id = variant_link()
    source_id = source_link()
    service_speed = speed_column()
    min_working_days = db.Column(db.Integer)
    max_working_days = db.Column(db.Integer)
    duration_note = db.Column(db.String(200))
    starts_after = db.Column(
        db.String(20), nullable=False, default="unknown", server_default="unknown"
    )
    basis = db.Column(
        db.String(20), nullable=False, default="unverified", server_default="unverified"
    )
    delay_factors = db.Column(db.Text)

    service = db.relationship("GovernmentService", back_populates="processing")
    variant = db.relationship("ServiceVariant")
    source = db.relationship("OfficialSource")

    def __repr__(self):
        return f"<ProcessingInformation service={self.service_id}>"


class ServiceStep(db.Model):
    __tablename__ = "service_steps"
    __table_args__ = (
        minimum_check("step_number", 1, nullable=False),
        choice_check("stage", STEP_STAGES),
        web_link_check("action_url"),
    )

    id = db.Column(db.Integer, primary_key=True)
    service_id = service_link()
    variant_id = variant_link()
    source_id = source_link()
    step_number = db.Column(db.Integer, nullable=False)
    stage = db.Column(
        db.String(20), nullable=False, default="before_visit", server_default="before_visit"
    )
    title = db.Column(db.String(200), nullable=False)
    instructions = db.Column(db.Text)
    action_url = db.Column(db.String(500))

    service = db.relationship("GovernmentService", back_populates="steps")
    variant = db.relationship("ServiceVariant")
    source = db.relationship("OfficialSource")

    def __repr__(self):
        return f"<ServiceStep {self.step_number}: {self.title}>"
