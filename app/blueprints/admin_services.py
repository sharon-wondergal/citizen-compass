"""Managing government services and everything on their checklists."""

from dataclasses import dataclass

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select
from sqlalchemy.orm import joinedload, selectinload

from app.blueprints.admin import EDIT_ROLES, admin_bp
from app.extensions import db
from app.forms.admin import (
    DocumentForm,
    FeeForm,
    OfficeLinkForm,
    ProcessingForm,
    ServiceForm,
    StepForm,
    VariantForm,
)
from app.logic.auth import role_required
from app.logic.checklist import BASIS_LABELS, describe_duration
from app.logic.records import (
    apply_form,
    delete_record,
    reset_section,
    save_change,
    set_archived,
    snapshot,
    unique_slug,
)
from app.logic.search import clean_query, like_pattern, paginate
from app.logic.verification import (
    STATUS_LABELS,
    create_verification_records,
    overall_status,
    section_statuses,
)
from app.models import (
    GovernmentService,
    ProcessingInformation,
    RequiredDocument,
    ServiceFee,
    ServiceOffice,
    ServiceStep,
    ServiceVariant,
)
from app.models.base import VERIFICATION_SECTIONS

DUPLICATE_MESSAGE = "That couldn't be saved because the name is already in use."


@dataclass
class DetailKind:
    """One type of row on a checklist, and the section it belongs to."""

    model: type
    form: type
    singular: str
    section: str


DETAIL_KINDS = {
    "variants": DetailKind(ServiceVariant, VariantForm, "situation", "overview"),
    "steps": DetailKind(ServiceStep, StepForm, "step", "overview"),
    "documents": DetailKind(RequiredDocument, DocumentForm, "document", "documents"),
    "fees": DetailKind(ServiceFee, FeeForm, "fee", "fees"),
    "processing": DetailKind(ProcessingInformation, ProcessingForm, "processing time", "processing"),
}
KIND_NAMES = "any(variants,steps,documents,fees,processing)"


def get_service_or_404(service_id):
    service = db.session.get(GovernmentService, service_id)
    if service is None:
        abort(404)
    return service


def get_item_or_404(kind, service, item_id):
    """The row must belong to the service named in the web address."""
    item = db.session.get(kind.model, item_id)
    if item is None or item.service_id != service.id:
        abort(404)
    return item


def manage_url(service):
    return url_for("admin.manage_service", service_id=service.id)


# ---------- The list of services ----------

@admin_bp.route("/services")
@login_required
def services():
    query = clean_query(request.args.get("q", ""))
    statement = (
        select(GovernmentService)
        .options(
            joinedload(GovernmentService.institution),
            selectinload(GovernmentService.verification_records),
        )
        .order_by(GovernmentService.is_archived, GovernmentService.name)
    )
    if query:
        statement = statement.where(
            GovernmentService.name.ilike(like_pattern(query.lower()), escape="\\")
        )

    rows = [
        {"service": service, "status": overall_status(service)}
        for service in db.session.scalars(statement).unique()
    ]
    page = max(request.args.get("page", default=1, type=int) or 1, 1)
    return render_template(
        "admin/services.html",
        results=paginate(rows, page),
        query=query,
        status_labels=STATUS_LABELS,
    )


# ---------- Creating and editing a service ----------

@admin_bp.route("/services/new", methods=["GET", "POST"])
@role_required(*EDIT_ROLES)
def new_service():
    form = ServiceForm()
    form.load_choices()

    if form.validate_on_submit():
        service = GovernmentService(created_by_id=current_user.id)
        apply_form(form, service)
        service.slug = unique_slug(GovernmentService, service.name)
        create_verification_records(service)

        if save_change(service, {}, current_user):
            flash("Service added. Every section starts as pending verification.", "success")
            return redirect(manage_url(service))
        flash(DUPLICATE_MESSAGE, "danger")

    return render_template(
        "admin/form.html", form=form, title="Add a service",
        back_url=url_for("admin.services"),
    )


@admin_bp.route("/services/<int:service_id>/edit", methods=["GET", "POST"])
@role_required(*EDIT_ROLES)
def edit_service(service_id):
    service = get_service_or_404(service_id)
    form = ServiceForm(obj=service)
    form.load_choices()

    if form.validate_on_submit():
        before = snapshot(service)
        apply_form(form, service)

        def on_change(old, new):
            reset_section(service, "overview", current_user)

        if save_change(service, before, current_user, on_change):
            flash("Service saved.", "success")
            return redirect(manage_url(service))
        flash(DUPLICATE_MESSAGE, "danger")

    return render_template(
        "admin/form.html", form=form, title=f"Edit {service.name}", back_url=manage_url(service),
    )


@admin_bp.route("/services/<int:service_id>/archive", methods=["POST"])
@role_required(*EDIT_ROLES)
def archive_service(service_id):
    service = get_service_or_404(service_id)
    set_archived(service, not service.is_archived, current_user)
    flash("Service restored." if not service.is_archived else "Service archived.", "success")
    return redirect(manage_url(service))


# ---------- The management page ----------

@admin_bp.route("/services/<int:service_id>")
@login_required
def manage_service(service_id):
    service = get_service_or_404(service_id)
    statuses = section_statuses(service)
    return render_template(
        "admin/service_manage.html",
        service=service,
        service_id=service.id,
        overall=overall_status(service),
        sections=[(section, statuses[section]) for section in VERIFICATION_SECTIONS],
        status_labels=STATUS_LABELS,
        basis_labels=BASIS_LABELS,
        describe_duration=describe_duration,
    )


# ---------- Checklist rows ----------

def save_row(kind, service, item, before, form):
    apply_form(form, item)

    def on_change(old, new):
        if kind.model is ServiceVariant and item.is_default:
            # Only one situation can be shown first.
            for other in service.variants:
                if other is not item:
                    other.is_default = False
        reset_section(service, kind.section, current_user)

    return save_change(item, before, current_user, on_change)


@admin_bp.route(f"/services/<int:service_id>/<{KIND_NAMES}:kind_name>/new", methods=["GET", "POST"])
@role_required(*EDIT_ROLES)
def new_row(service_id, kind_name):
    service = get_service_or_404(service_id)
    kind = DETAIL_KINDS[kind_name]
    form = kind.form()
    form.load_choices(service)

    if form.validate_on_submit():
        if save_row(kind, service, kind.model(service_id=service.id), {}, form):
            flash(f"The {kind.singular} was added.", "success")
            return redirect(manage_url(service))
        flash(DUPLICATE_MESSAGE, "danger")

    return render_template(
        "admin/form.html", form=form, title=f"Add a {kind.singular}: {service.name}",
        back_url=manage_url(service),
    )


@admin_bp.route(
    f"/services/<int:service_id>/<{KIND_NAMES}:kind_name>/<int:item_id>/edit",
    methods=["GET", "POST"],
)
@role_required(*EDIT_ROLES)
def edit_row(service_id, kind_name, item_id):
    service = get_service_or_404(service_id)
    kind = DETAIL_KINDS[kind_name]
    item = get_item_or_404(kind, service, item_id)
    form = kind.form(obj=item)
    form.load_choices(service)

    if form.validate_on_submit():
        if save_row(kind, service, item, snapshot(item), form):
            flash(f"The {kind.singular} was saved.", "success")
            return redirect(manage_url(service))
        flash(DUPLICATE_MESSAGE, "danger")

    return render_template(
        "admin/form.html", form=form, title=f"Edit {kind.singular}: {service.name}",
        back_url=manage_url(service),
    )


@admin_bp.route(
    f"/services/<int:service_id>/<{KIND_NAMES}:kind_name>/<int:item_id>/delete", methods=["POST"]
)
@role_required(*EDIT_ROLES)
def delete_row(service_id, kind_name, item_id):
    service = get_service_or_404(service_id)
    kind = DETAIL_KINDS[kind_name]
    item = get_item_or_404(kind, service, item_id)

    def on_change():
        # Deleting a situation also removes its rows from other sections.
        sections = VERIFICATION_SECTIONS if kind.model is ServiceVariant else (kind.section,)
        for section in sections:
            reset_section(service, section, current_user)

    if delete_record(item, current_user, on_change):
        flash(f"The {kind.singular} was deleted.", "success")
    else:
        flash("That couldn't be deleted because other records depend on it.", "danger")
    return redirect(manage_url(service))


# ---------- Offices offering the service ----------

@admin_bp.route("/services/<int:service_id>/offices/new", methods=["GET", "POST"])
@role_required(*EDIT_ROLES)
def new_office_link(service_id):
    service = get_service_or_404(service_id)
    form = OfficeLinkForm()
    form.load_choices()

    if form.validate_on_submit():
        link = ServiceOffice(service_id=service.id)
        apply_form(form, link)

        def on_change(old, new):
            reset_section(service, "offices", current_user)

        if save_change(link, {}, current_user, on_change):
            flash("Office linked. The link starts as pending verification.", "success")
            return redirect(manage_url(service))
        flash("That office is already linked to this service.", "danger")

    return render_template(
        "admin/form.html", form=form, title=f"Link an office: {service.name}",
        back_url=manage_url(service),
    )


@admin_bp.route("/services/<int:service_id>/offices/<int:link_id>/delete", methods=["POST"])
@role_required(*EDIT_ROLES)
def delete_office_link(service_id, link_id):
    service = get_service_or_404(service_id)
    link = db.session.get(ServiceOffice, link_id)
    if link is None or link.service_id != service.id:
        abort(404)

    delete_record(link, current_user, lambda: reset_section(service, "offices", current_user))
    flash("Office removed from this service.", "success")
    return redirect(manage_url(service))
