"""The administrator area. Every route here requires a signed-in administrator."""

from flask import Blueprint, render_template
from flask_login import login_required

from app.logic.auth import ROLE_LABELS
from app.logic.dashboard import build_dashboard

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.after_request
def keep_pages_private(response):
    """Stop browsers and search engines from keeping these pages."""
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex"
    return response


@admin_bp.context_processor
def admin_template_values():
    return {"role_labels": ROLE_LABELS}


@admin_bp.route("")
@login_required
def dashboard():
    return render_template("admin/dashboard.html", dashboard=build_dashboard())
