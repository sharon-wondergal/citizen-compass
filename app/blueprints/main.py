"""General pages: the homepage, information pages and the health check."""

from flask import Blueprint, jsonify, render_template

from app.logic.home import (
    categories_with_counts,
    featured_services,
    institutions_with_counts,
    quick_tags,
    site_counts,
)
from app.logic.system import check_database
from app.logic.verification import overall_status

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    heading, intro, services = featured_services()
    featured = [
        {"service": service, "status": overall_status(service)} for service in services
    ]
    return render_template(
        "main/index.html",
        featured_heading=heading,
        featured_intro=intro,
        featured=featured,
        # Only categories with something to open appear on the homepage.
        categories=[row for row in categories_with_counts() if row[1]],
        institutions=institutions_with_counts(),
        counts=site_counts(),
        tags=quick_tags(),
    )


@main_bp.route("/disclaimer")
def disclaimer():
    return render_template("main/disclaimer.html")


@main_bp.route("/privacy")
def privacy():
    return render_template("main/privacy.html")


@main_bp.route("/health")
def health():
    """A small status check that monitoring tools can call."""
    database = check_database()
    if database["connected"] and database["foreign_keys"]:
        return jsonify(status="ok")
    return jsonify(status="unavailable"), 503
