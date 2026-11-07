"""The government service directory, search and preparation checklists."""

from datetime import date

from flask import Blueprint, abort, jsonify, render_template, request

from app.extensions import db, limiter
from app.logic.analytics import record_service_view
from app.logic.checklist import build_checklist, choose_variant, get_service
from app.logic.quick_answer import find_answer
from app.logic.search import (
    MODE_LABELS,
    clean_query,
    filter_options,
    log_search,
    parse_filters,
    run_search,
    spelling_suggestion,
    suggest_services,
)
from app.models import District, Region

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


@services_bp.route("/services/quick-answer")
@limiter.limit("60 per minute")
def quick_answer():
    """The short answer shown on the homepage."""
    query = clean_query(request.args.get("q", ""))
    if not query:
        return jsonify(found=False, query="", suggestion=None)
    return jsonify(find_answer(query))


@services_bp.route("/services/<slug>")
@limiter.limit("120 per minute")
def detail(slug):
    service = get_service(slug)
    if service is None:
        abort(404)

    # Unknown values in the web address simply find nothing and are ignored.
    variant = choose_variant(service, request.args.get("variant", type=int))
    district_id = request.args.get("district", type=int)
    region_id = request.args.get("region", type=int)
    district = db.session.get(District, district_id) if district_id else None
    region = db.session.get(Region, region_id) if region_id else None

    page = render_template(
        "services/detail.html",
        checklist=build_checklist(
            service, variant, district=district, region_id=region.id if region else None
        ),
        district=district,
        region=region,
        districts=db.session.scalars(db.select(District).order_by(District.name)).all(),
        regions=db.session.scalars(db.select(Region).order_by(Region.name)).all(),
        today=date.today(),
    )

    # Counted after the page is built, because saving refreshes the loaded data.
    record_service_view(service.id)
    return page
