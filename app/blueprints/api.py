"""A read-only JSON API, so other applications can use the directory.

Only GET requests exist, so nothing can be changed through the API. Unlike the
web pages, the API refuses unknown values with a clear error instead of
ignoring them, because another program can fix its request.
"""

from flask import Blueprint, jsonify, request, url_for

from app.extensions import limiter
from app.logic.api_data import (
    checklist_data,
    institution_data,
    office_data,
    service_summary,
)
from app.logic.checklist import get_service
from app.logic.directory import (
    find_institutions,
    find_offices,
    get_institution,
    office_filter_options,
    parse_institution_filters,
    parse_office_filters,
)
from app.logic.home import categories_with_counts
from app.logic.search import RESULTS_PER_PAGE, filter_options, parse_filters, run_search

api_bp = Blueprint("api", __name__, url_prefix="/api/v1")

# One limit for every API route. Each connection gets 120 requests a minute.
limiter.limit("120 per minute")(api_bp)


class ApiError(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


@api_bp.errorhandler(ApiError)
def api_error(error):
    return jsonify(error={"code": error.code, "message": error.message}), error.status


def check_request(allowed, parsed):
    """Refuse unknown parameters, unknown values and bad page numbers."""
    unknown = sorted(set(request.args) - set(allowed))
    if unknown:
        raise ApiError(400, "unknown_parameter", f"Unknown parameter: {', '.join(unknown)}.")

    raw_page = request.args.get("page")
    if raw_page is not None and (not raw_page.isdigit() or int(raw_page) < 1):
        raise ApiError(400, "invalid_value", "'page' must be a whole number of 1 or more.")

    for name, value in parsed.items():
        if request.args.get(name) and not value:
            raise ApiError(400, "invalid_value", f"Unknown value for '{name}'.")


def page_meta(results):
    return {
        "page": results.page,
        "pages": results.pages,
        "total": results.total,
        "per_page": RESULTS_PER_PAGE,
    }


def not_found(thing):
    raise ApiError(404, "not_found", f"No {thing} was found at this address.")


@api_bp.get("")
def index():
    """A list of the available endpoints."""
    return jsonify(
        name="Citizen Compass API",
        version="1",
        notice="Independent project, not a government service. Unverified fee amounts are "
               "never included. Always confirm details with the responsible agency.",
        endpoints={
            "services": url_for("api.services"),
            "service": url_for("api.service", slug="SLUG"),
            "checklist": url_for("api.checklist", slug="SLUG"),
            "institutions": url_for("api.institutions"),
            "institution": url_for("api.institution", slug="SLUG"),
            "offices": url_for("api.offices"),
            "categories": url_for("api.categories"),
        },
    )


@api_bp.get("/services")
def services():
    options = filter_options()
    filters = parse_filters(request.args, options)
    check_request(
        {"q", "category", "institution", "region", "district", "mode", "status", "page"},
        {
            "category": filters.category, "institution": filters.institution,
            "region": filters.region, "district": filters.district,
            "mode": filters.mode, "status": filters.status,
        },
    )
    results = run_search(filters)
    return jsonify(
        data=[service_summary(item["service"]) for item in results.items],
        meta=page_meta(results),
    )


@api_bp.get("/services/<slug>")
def service(slug):
    check_request(set(), {})
    found = get_service(slug)
    if found is None:
        not_found("service")
    return jsonify(data={
        **service_summary(found),
        "checklist": url_for("api.checklist", slug=found.slug),
        "web_page": url_for("services.detail", slug=found.slug),
    })


@api_bp.get("/services/<slug>/checklist")
def checklist(slug):
    found = get_service(slug)
    if found is None:
        not_found("service")

    situation = request.args.get("situation", type=int)
    valid_situation = situation if situation in {v.id for v in found.variants} else None
    check_request({"situation"}, {"situation": valid_situation})
    return jsonify(data=checklist_data(found, valid_situation))


@api_bp.get("/institutions")
def institutions():
    filters = parse_institution_filters(request.args)
    check_request({"q", "type", "page"}, {"type": filters.institution_type})
    results = find_institutions(filters)
    return jsonify(
        data=[institution_data(item["institution"]) for item in results.items],
        meta=page_meta(results),
    )


@api_bp.get("/institutions/<slug>")
def institution(slug):
    check_request(set(), {})
    found = get_institution(slug)
    if found is None:
        not_found("institution")
    return jsonify(data=institution_data(found, detailed=True))


@api_bp.get("/offices")
def offices():
    options = office_filter_options()
    filters = parse_office_filters(request.args, options)
    check_request(
        {"district", "region", "institution", "service", "page"},
        {
            "district": filters.district, "region": filters.region,
            "institution": filters.institution, "service": filters.service,
        },
    )
    results, empty_district = find_offices(filters)
    return jsonify(
        data=[office_data(item["office"]) for item in results.items],
        meta={
            **page_meta(results),
            # Set when the chosen district had no office, so the region was used instead.
            "no_office_in_district": empty_district,
        },
    )


@api_bp.get("/categories")
def categories():
    check_request(set(), {})
    return jsonify(data=[
        {"slug": category.slug, "name": category.name, "services": count}
        for category, count in categories_with_counts()
    ])
