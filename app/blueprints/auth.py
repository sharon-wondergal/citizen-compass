"""Administrator sign in and sign out."""

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.extensions import db, limiter
from app.forms.auth import LoginForm
from app.logic.audit import record_audit
from app.logic.auth import LOGIN_FAILED_MESSAGE, authenticate, is_safe_next

auth_bp = Blueprint("auth", __name__, url_prefix="/admin")


@auth_bp.after_request
def keep_pages_private(response):
    """Stop browsers and search engines from keeping these pages."""
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex"
    return response


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("admin.dashboard"))

    form = LoginForm()
    if form.validate_on_submit():
        user = authenticate(form.email.data, form.password.data)
        if user:
            # A fresh session stops anyone reusing one from before login.
            session.clear()
            login_user(user)
            session.permanent = True
            record_audit(user, "login", "admin_users", user.id, user.email)
            db.session.commit()

            target = request.args.get("next")
            return redirect(target if is_safe_next(target) else url_for("admin.dashboard"))
        flash(LOGIN_FAILED_MESSAGE, "danger")

    return render_template("admin/login.html", form=form)


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    session.clear()
    flash("You've signed out.", "success")
    return redirect(url_for("auth.login"))
