"""General pages. Stage 6 replaces this temporary home page with the real one."""

from flask import Blueprint, jsonify, render_template

from app.logic.system import check_database

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    return render_template("main/index.html", database=check_database())


@main_bp.route("/health")
def health():
    """A small status check that monitoring tools can call."""
    database = check_database()
    if database["connected"] and database["foreign_keys"]:
        return jsonify(status="ok")
    return jsonify(status="unavailable"), 503
