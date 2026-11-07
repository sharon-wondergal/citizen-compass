"""Forms for recording a verification decision."""

from datetime import date

from flask_wtf import FlaskForm
from wtforms import DateField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional

from app.forms.admin import blank_to_none, optional_menu, source_choices, web_link
from app.logic.verification import STATUS_LABELS


class ReviewForm(FlaskForm):
    status = SelectField("Your decision", choices=list(STATUS_LABELS.items()))
    last_checked_on = DateField(
        "Date you checked the source", validators=[DataRequired("Enter the date you checked.")]
    )
    review_due_on = DateField(
        "Next review date",
        validators=[Optional()],
        description="Required when verifying. Fees often change each financial year.",
    )
    submit = SubmitField("Save decision")

    needs_review_date = True

    def add_error(self, field, message):
        field.errors = [*field.errors, message]

    def evidence_is_missing(self):
        """Forms below say what counts as evidence."""
        return False

    def validate(self, extra_validators=None):
        """Check the fields together. Optional() skips rules on blank fields."""
        valid = super().validate(extra_validators)
        checked = self.last_checked_on.data

        if checked and checked > date.today():
            self.add_error(self.last_checked_on, "The check date can't be in the future.")
            valid = False

        if self.status.data == "verified":
            if self.needs_review_date and not self.review_date_is_valid(checked):
                valid = False
            if self.evidence_is_missing():
                valid = False
        return valid

    def review_date_is_valid(self, checked):
        due = self.review_due_on.data
        if due is None:
            self.add_error(self.review_due_on, "Enter a review date to verify this.")
            return False
        if checked and due <= checked:
            self.add_error(self.review_due_on, "The review date must be after the check date.")
            return False
        return True


class SourceReviewForm(ReviewForm):
    """A review backed by a record in the official sources list."""

    source_id = optional_menu("Official source you checked")

    def load_choices(self):
        self.source_id.choices = source_choices()

    def evidence_is_missing(self):
        if self.source_id.data is None:
            self.add_error(self.source_id, "Choose the official source you checked.")
            return True
        return False


class SectionReviewForm(SourceReviewForm):
    notes = TextAreaField(
        "Notes for other administrators", validators=[Optional()], filters=[blank_to_none],
    )


class LinkReviewForm(SourceReviewForm):
    """An office link follows the review cycle of its service's offices section."""

    review_due_on = None  # Removes this field from the form.
    needs_review_date = False


class InstitutionReviewForm(ReviewForm):
    source_url = StringField(
        "Official page you checked",
        validators=[Optional(), Length(max=500), web_link],
        filters=[blank_to_none],
    )

    def load_choices(self):
        """This form has no menus to fill."""

    def evidence_is_missing(self):
        if not self.source_url.data:
            self.add_error(self.source_url, "Enter the official page you checked.")
            return True
        return False
