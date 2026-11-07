"""The citizen report form. It asks for as little as possible."""

from flask_wtf import FlaskForm
from wtforms import SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional

from app.forms.admin import blank_to_none, optional_id
from app.logic.reports import PROBLEM_LABELS, open_service_choices


class ReportForm(FlaskForm):
    service_id = SelectField(
        "Which service is it about?", coerce=optional_id, validators=[Optional()]
    )
    service_name = StringField(
        "If it isn't listed, type the service name",
        validators=[Optional(), Length(max=200)],
        filters=[blank_to_none],
    )
    problem_type = SelectField("What's the problem?", choices=list(PROBLEM_LABELS.items()))
    description = TextAreaField(
        "What's wrong?",
        validators=[
            DataRequired("Tell us what's wrong."),
            Length(min=10, max=2000, message="Use between 10 and 2,000 characters."),
        ],
        filters=[blank_to_none],
        description="Please don't include ID numbers, passwords or payment details.",
    )
    contact_info = StringField(
        "Your phone or email (optional)",
        validators=[Optional(), Length(max=200)],
        filters=[blank_to_none],
        description="Only used if we need to ask about this report.",
    )
    # Hidden from people. Automated spam tools tend to fill in every field.
    website = StringField("Leave this field empty")
    submit = SubmitField("Send report")

    def load_choices(self):
        self.service_id.choices = [("", "Choose a service")] + open_service_choices()

    def validate(self, extra_validators=None):
        valid = super().validate(extra_validators)
        if self.service_id.data is None and not self.service_name.data:
            self.service_name.errors = [
                *self.service_name.errors, "Choose a service or type its name."
            ]
            return False
        return valid
