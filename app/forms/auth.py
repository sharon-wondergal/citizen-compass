"""The administrator login form."""

from flask_wtf import FlaskForm
from wtforms import EmailField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Length


class LoginForm(FlaskForm):
    email = EmailField(
        "Email address",
        validators=[DataRequired("Enter your email address."), Length(max=255)],
    )
    password = PasswordField(
        "Password",
        validators=[DataRequired("Enter your password."), Length(max=128)],
    )
    submit = SubmitField("Sign in")
