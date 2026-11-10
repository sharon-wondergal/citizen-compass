"""The form for recording a decision on a citizen report."""

from flask_wtf import FlaskForm
from wtforms import SelectField, SubmitField, TextAreaField
from wtforms.validators import Length, Optional

from app.forms.admin import blank_to_none
from app.logic.report_review import CLOSED_STATUSES, REPORT_STATUS_LABELS


class ReportReviewForm(FlaskForm):
    status = SelectField("Status", choices=list(REPORT_STATUS_LABELS.items()))
    action_taken = TextAreaField(
        "What was checked and done",
        validators=[Optional(), Length(max=2000)],
        filters=[blank_to_none],
        description="Required to resolve or dismiss. Name the official source you checked.",
    )
    submit = SubmitField("Save")

    def validate(self, extra_validators=None):
        valid = super().validate(extra_validators)
        if self.status.data in CLOSED_STATUSES and not self.action_taken.data:
            self.action_taken.errors = [
                *self.action_taken.errors, "Describe what was checked and done before closing."
            ]
            return False
        return valid
