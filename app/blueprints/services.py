"""The government service directory and search."""

from flask import Blueprint, jsonify, render_template, request

from app.extensions import limiter
from app.logic.search import (
    MODE_LABELS,
    filter_options,
    log_search,
    parse_filters,
    run_search,
    spelling_suggestion,
    suggest_services,
)

services_bp = Blueprint("services", __name__)


@services_bp.route("/services")
@limiter.limit("60 per minute")
def search():
    options = filter_options()
    filters = parse_filters(request.args, options)
    results = run_search(filters)
    log_search(filters, results)

    suggestion = None
    if results.total == 0 and filters.query:
        suggestion = spelling_suggestion(filters.query)

    return render_template(
        "services/search.html",
        filters=filters,
        options=options,
        results=results,
        suggestion=suggestion,
        mode_labels=MODE_LABELS,
    )


@services_bp.route("/services/suggestions")
@limiter.limit("120 per minute")
def suggestions():
    return jsonify(suggestions=suggest_services(request.args.get("q", "")))
