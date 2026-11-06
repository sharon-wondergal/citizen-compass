"""Forms for managing records.

Field names match the database columns, so apply_form() can copy them across.

Empty matters here. A blank fee means "not confirmed", and 0 means "free", so
optional fields become None when left blank, never 0 or False.
"""

from flask_wtf import FlaskForm
from sqlalchemy import select
from wtforms import (
    BooleanField,
    DateField,
    FloatField,
    IntegerField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Email, Length, NumberRange, Optional, ValidationError

from app.extensions import db
from app.logic.checklist import BASIS_LABELS, STAGE_LABELS, STARTS_AFTER_LABELS
from app.logic.directory import INSTITUTION_TYPE_LABELS
from app.logic.search import MODE_LABELS
from app.models import (
    District,
    GovernmentInstitution,
    GovernmentOffice,
    OfficialSource,
    Region,
    ServiceCategory,
)
from app.models.base import SOURCE_TYPES

OFFICE_TYPE_LABELS = {
    "district": "District office",
    "service_centre": "Service centre",
    "regional": "Regional office",
    "headquarters": "Headquarters",
    "other": "Other",
}
SPEED_CHOICES = [
    ("not_applicable", "Not applicable"),
    ("ordinary", "Ordinary"),
    ("express", "Express"),
]
YES_NO_CHOICES = [("", "Not confirmed"), ("yes", "Yes"), ("no", "No")]


# ---------- Field helpers ----------

def blank_to_none(value):
    """Tidy text, and store blank fields as empty rather than as ""."""
    if isinstance(value, str):
        value = value.strip()
    return value or None


def optional_id(value):
    """Used by menus where "none" is a valid choice."""
    return None if value in ("", None) else int(value)


def optional_bool(value):
    """Yes, no, or not confirmed."""
    if isinstance(value, bool):
        return value
    return {"yes": True, "no": False}.get(value)


def web_link(form, field):
    if field.data and not field.data.lower().startswith(("http://", "https://")):
        raise ValidationError("Enter a full web address starting with http:// or https://.")


def text(label, maximum, required=False, **options):
    first = DataRequired(f"Enter the {label.lower()}.") if required else Optional()
    return StringField(
        label, validators=[first, Length(max=maximum)], filters=[blank_to_none], **options
    )


def long_text(label, **options):
    return TextAreaField(label, validators=[Optional()], filters=[blank_to_none], **options)


def link(label, **options):
    return StringField(
        label,
        validators=[Optional(), Length(max=500), web_link],
        filters=[blank_to_none],
        **options,
    )


def whole_number(label, minimum=0, **options):
    return IntegerField(
        label, validators=[Optional(), NumberRange(min=minimum)], **options
    )


def optional_menu(label, **options):
    return SelectField(label, coerce=optional_id, validators=[Optional()], **options)


def required_menu(label):
    return SelectField(label, coerce=int, validators=[DataRequired(f"Choose the {label.lower()}.")])


def yes_no_menu(label):
    return SelectField(label, choices=YES_NO_CHOICES, coerce=optional_bool, validators=[Optional()])


def sort_position():
    return IntegerField(
        "Display position", default=0, validators=[Optional(), NumberRange(min=0)],
        description="Lower numbers appear first.",
    )


# ---------- Menu choices ----------

def choices_for(model, label="name"):
    column = getattr(model, label)
    statement = select(model).order_by(column)
    if hasattr(model, "is_archived"):
        statement = statement.where(model.is_archived.is_(False))
    return [(item.id, getattr(item, label)) for item in db.session.scalars(statement)]


def source_choices():
    return [("", "No source yet")] + choices_for(OfficialSource, "title")


def variant_choices(service):
    """Only this service's variants can be chosen, so a row can't use another's."""
    variants = [(variant.id, variant.name) for variant in service.variants]
    return [("", "All situations")] + variants


class RecordForm(FlaskForm):
    submit = SubmitField("Save")

    def load_choices(self, context=None):
        """Fill the menus. Forms with menus replace this."""


# ---------- Services ----------

class ServiceForm(RecordForm):
    name = text("Service name", 200, required=True)
    summary = text("Short summary", 300, required=True)
    description = long_text("Description")
    eligibility = long_text("Who qualifies")
    institution_id = required_menu("Responsible institution")
    category_id = required_menu("Category")
    delivery_mode = SelectField(
        "How it's provided",
        choices=[("", "Not confirmed")] + list(MODE_LABELS.items()),
        coerce=blank_to_none,
        validators=[Optional()],
    )
    online_url = link("Official portal address")
    keywords = text(
        "Search keywords", 500,
        description="Everyday words and other names people might search for.",
    )
    is_demo = BooleanField(
        "This is a demonstration record",
        description="Demonstration records can never be verified.",
    )

    def load_choices(self, context=None):
        self.institution_id.choices = choices_for(GovernmentInstitution)
        self.category_id.choices = choices_for(ServiceCategory)


class VariantForm(RecordForm):
    name = text("Situation name", 120, required=True, description="For example: new, renewal or lost.")
    description = long_text("Description")
    is_default = BooleanField("Show this situation first")
    display_order = sort_position()


class DetailForm(RecordForm):
    """A row on a checklist, which can apply to one situation and cite a source."""

    variant_id = optional_menu("Applies to")
    source_id = optional_menu("Official source")

    def load_choices(self, context=None):
        self.variant_id.choices = variant_choices(context)
        self.source_id.choices = source_choices()


class DocumentForm(DetailForm):
    name = text("Document name", 200, required=True)
    is_mandatory = BooleanField("Citizens must bring this", default=True)
    original_required = yes_no_menu("Original required?")
    photocopies = whole_number("Photocopies", description="Leave blank if not confirmed. 0 means none.")
    certified_copy_accepted = yes_no_menu("Certified copy accepted?")
    max_age_days = whole_number("Must be issued within (days)", minimum=1)
    instructions = long_text("Instructions")
    display_order = sort_position()


class FeeForm(DetailForm):
    fee_name = text("Fee name", 200, required=True)
    fee_kind = SelectField(
        "Type", choices=[("official", "Official fee"), ("other_charge", "Other charge")]
    )
    service_speed = SelectField("Service speed", choices=SPEED_CHOICES)
    amount_ugx = whole_number(
        "Amount in UGX",
        description="Leave blank if not confirmed. 0 means the service is free.",
    )
    is_mandatory = BooleanField("Everyone must pay this", default=True)
    payment_method = text("Payment method", 200)
    payment_instructions = long_text("Payment instructions")
    effective_from = DateField("Applies from", validators=[Optional()])
    display_order = sort_position()


class ProcessingForm(DetailForm):
    service_speed = SelectField("Service speed", choices=SPEED_CHOICES)
    min_working_days = whole_number("Minimum working days")
    max_working_days = whole_number("Maximum working days")
    duration_note = text("Note", 200)
    starts_after = SelectField("Time is counted from", choices=list(STARTS_AFTER_LABELS.items()))
    basis = SelectField("Type of estimate", choices=list(BASIS_LABELS.items()))
    delay_factors = long_text("Possible delays")

    def validate_max_working_days(self, field):
        low = self.min_working_days.data
        if low is not None and field.data is not None and low > field.data:
            raise ValidationError("The maximum can't be less than the minimum.")


class StepForm(DetailForm):
    step_number = IntegerField(
        "Step number", validators=[DataRequired("Enter the step number."), NumberRange(min=1)]
    )
    stage = SelectField("When", choices=list(STAGE_LABELS.items()))
    title = text("Step title", 200, required=True)
    instructions = long_text("Instructions")
    action_url = link("Official page for this step")


class OfficeLinkForm(RecordForm):
    office_id = required_menu("Office")
    source_id = optional_menu("Official source")
    availability_note = text("Service note", 300)

    def load_choices(self, context=None):
        self.office_id.choices = choices_for(GovernmentOffice)
        self.source_id.choices = source_choices()


# ---------- Directory records ----------

class InstitutionForm(RecordForm):
    name = text("Institution name", 200, required=True)
    acronym = text("Acronym", 20)
    institution_type = SelectField("Type", choices=list(INSTITUTION_TYPE_LABELS.items()))
    description = long_text("Description")
    parent_id = optional_menu("Parent ministry")
    website = link("Official website")
    phone = text("Telephone", 50)
    email = StringField(
        "Email",
        validators=[Optional(), Length(max=255), Email("Enter a valid email address.")],
        filters=[blank_to_none],
    )
    headquarters = text("Headquarters", 300)
    source_url = link("Source of these details")
    is_demo = BooleanField("This is a demonstration record")

    def load_choices(self, context=None):
        self.current = context
        options = choices_for(GovernmentInstitution)
        if context is not None:
            options = [option for option in options if option[0] != context.id]
        self.parent_id.choices = [("", "None")] + options

    def validate_parent_id(self, field):
        """Stop a loop, such as A being the parent of B and B the parent of A."""
        ancestor = db.session.get(GovernmentInstitution, field.data) if field.data else None
        while ancestor is not None:
            if self.current is not None and ancestor.id == self.current.id:
                raise ValidationError("An institution can't sit under itself.")
            ancestor = ancestor.parent


class OfficeForm(RecordForm):
    name = text("Office name", 200, required=True)
    institution_id = required_menu("Institution")
    district_id = required_menu("District")
    office_type = SelectField("Type", choices=list(OFFICE_TYPE_LABELS.items()))
    physical_address = text("Physical address", 300, description="Leave blank until confirmed.")
    phone = text("Telephone", 50)
    email = StringField(
        "Email",
        validators=[Optional(), Length(max=255), Email("Enter a valid email address.")],
        filters=[blank_to_none],
    )
    website = link("Website")
    opening_hours = text("Opening hours", 200)
    latitude = FloatField(
        "Latitude", validators=[Optional(), NumberRange(min=-90, max=90)],
        description="Leave blank until confirmed.",
    )
    longitude = FloatField(
        "Longitude", validators=[Optional(), NumberRange(min=-180, max=180)]
    )
    source_id = optional_menu("Official source")
    is_demo = BooleanField("This is a demonstration record")

    def load_choices(self, context=None):
        self.institution_id.choices = choices_for(GovernmentInstitution)
        self.district_id.choices = choices_for(District)
        self.source_id.choices = source_choices()

    def validate(self, extra_validators=None):
        """Check the two coordinates together.

        This is a form-level check because Optional() stops all checks on a
        blank field, so a rule on one field would miss the case it's needed for.
        """
        valid = super().validate(extra_validators)
        if (self.latitude.data is None) != (self.longitude.data is None):
            self.longitude.errors = [
                *self.longitude.errors, "Enter both latitude and longitude, or neither."
            ]
            return False
        return valid


class SourceForm(RecordForm):
    title = text("Source title", 300, required=True)
    url = StringField(
        "Web address",
        validators=[DataRequired("Enter the web address."), Length(max=500), web_link],
        filters=[blank_to_none],
    )
    institution_id = required_menu("Responsible institution")
    source_type = SelectField(
        "Type", choices=[(value, value.replace("_", " ").capitalize()) for value in SOURCE_TYPES]
    )
    published_on = DateField("Published on", validators=[Optional()])

    def load_choices(self, context=None):
        self.institution_id.choices = choices_for(GovernmentInstitution)


class CategoryForm(RecordForm):
    name = text("Category name", 120, required=True)
    description = long_text("Description")
    icon = text("Icon name", 50, description="A Bootstrap icon, such as bi-map.")
    display_order = sort_position()
    is_active = BooleanField("Show this category to citizens", default=True)


class RegionForm(RecordForm):
    name = text("Region name", 50, required=True)


class DistrictForm(RecordForm):
    name = text("District name", 80, required=True)
    region_id = required_menu("Region")
    sub_region = text("Sub-region", 80)

    def load_choices(self, context=None):
        self.region_id.choices = choices_for(Region)
