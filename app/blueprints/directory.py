"""The government institution directory and the office finder."""

from flask import Blueprint, abort, render_template, request

from app.extensions import limiter
from app.logic.analytics import record_institution_view
from app.logic.directory import (
    INSTITUTION_TYPE_LABELS,
    build_institution_page,
    find_institutions,
    find_offices,
    get_institution,
    office_filter_options,
    parse_institution_filters,
    parse_office_filters,
)

directory_bp = Blueprint("directory", __name__)


@directory_bp.route("/institutions")
@limiter.limit("60 per minute")
def institutions():
    filters = parse_institution_filters(request.args)
    return render_template(
        "directory/institutions.html",
        filters=filters,
        results=find_institutions(filters),
        type_labels=INSTITUTION_TYPE_LABELS,
    )


@directory_bp.route("/institutions/<slug>")
@limiter.limit("120 per minute")
def institution_detail(slug):
    institution = get_institution(slug)
    if institution is None:
        abort(404)

    page = render_template(
        "directory/institution_detail.html", details=build_institution_page(institution)
    )

    # Counted after the page is built, because saving refreshes the loaded data.
    record_institution_view(institution.id)
    return page


@directory_bp.route("/offices")
@limiter.limit("60 per minute")
def offices():
    options = office_filter_options()
    filters = parse_office_filters(request.args, options)
    results, empty_district = find_offices(filters)
    return render_template(
        "directory/offices.html",
        filters=filters,
        options=options,
        results=results,
        empty_district=empty_district,
    )
