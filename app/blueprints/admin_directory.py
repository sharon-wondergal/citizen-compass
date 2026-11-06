"""Managing institutions, offices, sources, categories, regions and districts.

These all work the same way, so one set of routes serves them. Each ManagedKind
below describes what's different about one type of record.
"""

from dataclasses import dataclass
from typing import Callable

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select

from app.blueprints.admin import EDIT_ROLES, admin_bp
from app.extensions import db
from app.forms.admin import (
    CategoryForm,
    DistrictForm,
    InstitutionForm,
    OfficeForm,
    RegionForm,
    SourceForm,
)
from app.logic.auth import role_required
from app.logic.directory import INSTITUTION_TYPE_LABELS, record_status
from app.logic.records import (
    apply_form,
    delete_record,
    reset_office,
    reset_record,
    reset_records_citing,
    save_change,
    set_archived,
    snapshot,
    unique_slug,
)
from app.logic.search import clean_query, like_pattern, paginate
from app.models import (
    District,
    GovernmentInstitution,
    GovernmentOffice,
    OfficialSource,
    Region,
    ServiceCategory,
)


def no_reset(record, admin, old, new):
    """Records with no verification status of their own."""


def reset_institution(record, admin, old, new):
    reset_record(record)


def reset_changed_office(record, admin, old, new):
    reset_office(record, admin)


def reset_moved_source(record, admin, old, new):
    """A new title changes nothing. A new address needs rechecking."""
    if "url" in new:
        reset_records_citing(record, admin)


@dataclass
class ManagedKind:
    model: type
    form: type
    singular: str
    plural: str
    subtitle: Callable
    name_column: str = "name"
    uses_slug: bool = False
    can_archive: bool = False
    has_status: bool = False
    on_change: Callable = no_reset


KINDS = {
    "institutions": ManagedKind(
        GovernmentInstitution, InstitutionForm, "institution", "Institutions",
        lambda item: INSTITUTION_TYPE_LABELS[item.institution_type],
        uses_slug=True, can_archive=True, has_status=True, on_change=reset_institution,
    ),
    "offices": ManagedKind(
        GovernmentOffice, OfficeForm, "office", "Offices",
        lambda item: f"{item.institution.name} · {item.district.name}",
        can_archive=True, has_status=True, on_change=reset_changed_office,
    ),
    "sources": ManagedKind(
        OfficialSource, SourceForm, "source", "Official sources",
        lambda item: item.url, name_column="title", on_change=reset_moved_source,
    ),
    "categories": ManagedKind(
        ServiceCategory, CategoryForm, "category", "Categories",
        lambda item: "Shown to citizens" if item.is_active else "Hidden from citizens",
        uses_slug=True,
    ),
    "regions": ManagedKind(
        Region, RegionForm, "region", "Regions",
        lambda item: f"{len(item.districts)} districts",
    ),
    "districts": ManagedKind(
        District, DistrictForm, "district", "Districts",
        lambda item: item.region.name,
    ),
}
KIND_NAMES = "any(institutions,offices,sources,categories,regions,districts)"


def get_kind(kind_name):
    return KINDS[kind_name]


def get_record_or_404(kind, record_id):
    record = db.session.get(kind.model, record_id)
    if record is None:
        abort(404)
    return record


def list_url(kind_name):
    return url_for("admin.records", kind_name=kind_name)


@admin_bp.route(f"/<{KIND_NAMES}:kind_name>")
@login_required
def records(kind_name):
    kind = get_kind(kind_name)
    column = getattr(kind.model, kind.name_column)
    query = clean_query(request.args.get("q", ""))

    statement = select(kind.model).order_by(column)
    if query:
        statement = statement.where(column.ilike(like_pattern(query.lower()), escape="\\"))

    rows = []
    for record in db.session.scalars(statement):
        row = {
            "record": record,
            "name": getattr(record, kind.name_column),
            "subtitle": kind.subtitle(record),
            "archived": getattr(record, "is_archived", False),
        }
        if kind.has_status:
            row.update(record_status(record))
        rows.append(row)

    page = max(request.args.get("page", default=1, type=int) or 1, 1)
    return render_template(
        "admin/records.html",
        kind=kind,
        kind_name=kind_name,
        results=paginate(rows, page),
        query=query,
    )


@admin_bp.route(f"/<{KIND_NAMES}:kind_name>/new", methods=["GET", "POST"])
@role_required(*EDIT_ROLES)
def new_record(kind_name):
    kind = get_kind(kind_name)
    form = kind.form()
    form.load_choices()

    if form.validate_on_submit():
        record = kind.model()
        apply_form(form, record)
        if kind.uses_slug:
            record.slug = unique_slug(kind.model, record.name)

        if save_change(record, {}, current_user):
            flash(f"The {kind.singular} was added.", "success")
            return redirect(list_url(kind_name))
        flash("That couldn't be saved because the name or address is already in use.", "danger")

    return render_template(
        "admin/form.html", form=form, title=f"Add {kind.singular}", back_url=list_url(kind_name),
    )


@admin_bp.route(f"/<{KIND_NAMES}:kind_name>/<int:record_id>/edit", methods=["GET", "POST"])
@role_required(*EDIT_ROLES)
def edit_record(kind_name, record_id):
    kind = get_kind(kind_name)
    record = get_record_or_404(kind, record_id)
    form = kind.form(obj=record)
    form.load_choices(record)

    if form.validate_on_submit():
        before = snapshot(record)
        apply_form(form, record)

        def on_change(old, new):
            kind.on_change(record, current_user, old, new)

        if save_change(record, before, current_user, on_change):
            flash(f"The {kind.singular} was saved.", "success")
            return redirect(list_url(kind_name))
        flash("That couldn't be saved because the name or address is already in use.", "danger")

    return render_template(
        "admin/form.html", form=form, title=f"Edit {kind.singular}", back_url=list_url(kind_name),
    )


def open_dependants(record):
    """What must be moved or archived before an institution can be archived."""
    services = [item for item in getattr(record, "services", []) if not item.is_archived]
    offices = [item for item in getattr(record, "offices", []) if not item.is_archived]
    return services + offices


@admin_bp.route(f"/<{KIND_NAMES}:kind_name>/<int:record_id>/archive", methods=["POST"])
@role_required(*EDIT_ROLES)
def archive_record(kind_name, record_id):
    kind = get_kind(kind_name)
    if not kind.can_archive:
        abort(404)
    record = get_record_or_404(kind, record_id)

    if not record.is_archived and open_dependants(record):
        flash("Archive this institution's services and offices first.", "danger")
    else:
        set_archived(record, not record.is_archived, current_user)
        flash(f"The {kind.singular} was updated.", "success")
    return redirect(list_url(kind_name))


@admin_bp.route(f"/<{KIND_NAMES}:kind_name>/<int:record_id>/delete", methods=["POST"])
@role_required(*EDIT_ROLES)
def delete_directory_record(kind_name, record_id):
    kind = get_kind(kind_name)
    if kind.can_archive:
        abort(404)  # These keep their history, so they're archived instead.
    record = get_record_or_404(kind, record_id)

    if delete_record(record, current_user):
        flash(f"The {kind.singular} was deleted.", "success")
    else:
        flash(f"This {kind.singular} is still in use, so it can't be deleted.", "danger")
    return redirect(list_url(kind_name))
