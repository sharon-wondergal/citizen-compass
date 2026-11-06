"""Values and functions that every template can use."""

from datetime import date

from flask import current_app

from app.logic.verification import STATUS_LABELS


def route_exists(endpoint):
    """True once a feature's page exists.

    Templates use this to hide links to features that aren't built yet, so no
    button ever leads nowhere. The link appears when the route is added.
    """
    return endpoint in current_app.view_functions


def register_template_helpers(app):
    @app.context_processor
    def template_values():
        return {
            "route_exists": route_exists,
            "status_labels": STATUS_LABELS,
            "current_year": date.today().year,
            "contact_email": app.config.get("CONTACT_EMAIL"),
        }
