"""Friendly error pages. Visitors never see technical details."""

from flask import render_template

from app.extensions import db


def register_error_handlers(app):
    @app.errorhandler(404)
    def page_not_found(error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(429)
    def too_many_requests(error):
        return render_template("errors/429.html"), 429

    @app.errorhandler(500)
    def server_error(error):
        # Clear any half-finished database work before showing the page.
        db.session.rollback()
        return render_template("errors/500.html"), 500
