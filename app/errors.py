"""Friendly error pages. Visitors never see technical details.

Requests to the JSON API get JSON errors instead of web pages.
"""

from flask import jsonify, render_template, request

from app.extensions import db

API_PREFIX = "/api/"

MESSAGES = {
    400: ("bad_request", "The request couldn't be understood."),
    403: ("forbidden", "You don't have permission for this."),
    404: ("not_found", "Nothing was found at this address."),
    405: ("method_not_allowed", "This address doesn't accept that kind of request."),
    429: ("too_many_requests", "Too many requests. Please wait a minute and try again."),
    500: ("server_error", "Something went wrong on our side."),
}


def error_response(status, template):
    if request.path.startswith(API_PREFIX):
        code, message = MESSAGES[status]
        return jsonify(error={"code": code, "message": message}), status
    return render_template(template), status


def register_error_handlers(app):
    @app.errorhandler(400)
    def bad_request(error):
        # Also shown when a form's security token has expired.
        return error_response(400, "errors/400.html")

    @app.errorhandler(403)
    def forbidden(error):
        return error_response(403, "errors/403.html")

    @app.errorhandler(404)
    def page_not_found(error):
        return error_response(404, "errors/404.html")

    @app.errorhandler(405)
    def method_not_allowed(error):
        if request.path.startswith(API_PREFIX):
            return error_response(405, "errors/404.html")
        return error

    @app.errorhandler(429)
    def too_many_requests(error):
        return error_response(429, "errors/429.html")

    @app.errorhandler(500)
    def server_error(error):
        # Clear any half-finished database work before showing the page.
        db.session.rollback()
        return error_response(500, "errors/500.html")
