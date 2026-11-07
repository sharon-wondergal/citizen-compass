"""Reviewing information against official sources, and the history of changes."""

from datetime import date

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.blueprints.admin import VERIFY_ROLES, admin_bp
from app.extensions import db
from app.forms.review import (
    InstitutionReviewForm,
    LinkReviewForm,
    SectionReviewForm,
    SourceReviewForm,
)
from app.logic.auth import role_required
from app.logic.review import (
    OWN_WORK_MESSAGE,
    ReviewRefused,
    audit_page,
    build_queue,
    default_review_date,
    last_editor_id,
    review_directory_record,
    review_office_link,
    review_section,
    section_problems,
    section_summary,
)
from app.models import (
    GovernmentInstitution,
    GovernmentOffice,
    GovernmentService,
    ServiceOffice,
)
from app.models.base import AUDIT_ACTIONS

SECTION_NAMES = "any(overview,documents,fees,offices,processing)"
DIRECTORY_NAMES = "any(institutions,offices)"
DIRECTORY_MODELS = {"institutions": GovernmentInstitution, "offices": GovernmentOffice}


def page_number():
    return max(request.args.get("page", default=1, type=int) or 1, 1)


def review_defaults(status, **extra):
    today = date.today()
    return {
        "status": status,
        "last_checked_on": today,
        "review_due_on": default_review_date(today),
        **extra,
    }


def show_review_page(form, title, back_url, summary, problems=(), own_work=False, is_demo=False,
                     source=None):
    return render_template(
        "admin/review.html",
        form=form,
        title=title,
        back_url=back_url,
        summary=summary,
        problems=problems,
        own_work=own_work,
        is_demo=is_demo,
        source=source,
        own_work_message=OWN_WORK_MESSAGE,
    )


@admin_bp.route("/verification")
@login_required
def verification_queue():
    return render_template("admin/verification.html", queue=build_queue())


@admin_bp.route(f"/services/<int:service_id>/review/<{SECTION_NAMES}:section>", methods=["GET", "POST"])
@role_required(*VERIFY_ROLES)
def review_service_section(service_id, section):
    service = db.session.get(GovernmentService, service_id)
    if service is None:
        abort(404)
    record = next(
        (item for item in service.verification_records if item.section == section), None
    )
    if record is None:
        abort(404)

    form = SectionReviewForm(
        data=review_defaults(record.status, source_id=record.source_id, notes=record.notes)
    )
    form.load_choices()
    back_url = url_for("admin.manage_service", service_id=service.id)

    if form.validate_on_submit():
        try:
            review_section(
                record, current_user, form.status.data, form.source_id.data,
                form.last_checked_on.data, form.review_due_on.data, form.notes.data,
            )
            flash("Your decision was saved.", "success")
            return redirect(back_url)
        except ReviewRefused as refusal:
            flash(str(refusal), "danger")

    return show_review_page(
        form,
        f"Review {section}: {service.name}",
        back_url,
        section_summary(service, section),
        section_problems(service, section),
        record.last_edited_by_id == current_user.id,
        service.is_demo,
        record.source,
    )


@admin_bp.route("/services/<int:service_id>/offices/<int:link_id>/review", methods=["GET", "POST"])
@role_required(*VERIFY_ROLES)
def review_link(service_id, link_id):
    link = db.session.get(ServiceOffice, link_id)
    if link is None or link.service_id != service_id:
        abort(404)

    form = LinkReviewForm(data={
        "status": link.verification_status,
        "last_checked_on": date.today(),
        "source_id": link.source_id,
    })
    form.load_choices()
    back_url = url_for("admin.manage_service", service_id=service_id)

    if form.validate_on_submit():
        try:
            review_office_link(
                link, current_user, form.status.data, form.source_id.data,
                form.last_checked_on.data,
            )
            flash("Your decision was saved.", "success")
            return redirect(back_url)
        except ReviewRefused as refusal:
            flash(str(refusal), "danger")

    return show_review_page(
        form,
        f"Review office link: {link.service.name}",
        back_url,
        [f"Does {link.office.name} offer this service?",
         f"Note: {link.availability_note or 'None'}"],
        own_work=last_editor_id("service_offices", link.id) == current_user.id,
        is_demo=link.service.is_demo or link.office.is_demo,
        source=link.source,
    )


def directory_summary(record):
    fields = [("Name", record.name), ("Telephone", record.phone), ("Email", record.email),
              ("Website", record.website)]
    if isinstance(record, GovernmentOffice):
        fields += [("Address", record.physical_address), ("District", record.district.name),
                   ("Opening hours", record.opening_hours)]
    else:
        fields.append(("Headquarters", record.headquarters))
    return [f"{label}: {value or 'Not confirmed'}" for label, value in fields]


@admin_bp.route(f"/<{DIRECTORY_NAMES}:kind_name>/<int:record_id>/review", methods=["GET", "POST"])
@role_required(*VERIFY_ROLES)
def review_record(kind_name, record_id):
    record = db.session.get(DIRECTORY_MODELS[kind_name], record_id)
    if record is None:
        abort(404)

    is_office = kind_name == "offices"
    if is_office:
        form = SourceReviewForm(
            data=review_defaults(record.verification_status, source_id=record.source_id)
        )
    else:
        form = InstitutionReviewForm(
            data=review_defaults(record.verification_status, source_url=record.source_url)
        )
    form.load_choices()
    back_url = url_for("admin.records", kind_name=kind_name)

    if form.validate_on_submit():
        field = "source_id" if is_office else "source_url"
        try:
            review_directory_record(
                record, current_user, form.status.data, form.last_checked_on.data,
                form.review_due_on.data, {field: form[field].data},
            )
            flash("Your decision was saved.", "success")
            return redirect(back_url)
        except ReviewRefused as refusal:
            flash(str(refusal), "danger")

    return show_review_page(
        form,
        f"Review: {record.name}",
        back_url,
        directory_summary(record),
        own_work=last_editor_id(record.__tablename__, record.id) == current_user.id,
        is_demo=record.is_demo,
        source=record.source if is_office else None,
    )


@admin_bp.route("/history")
@login_required
def history():
    action = request.args.get("action", "")
    if action not in AUDIT_ACTIONS:
        action = ""
    return render_template(
        "admin/history.html",
        results=audit_page(page_number(), action),
        action=action,
        actions=AUDIT_ACTIONS,
    )
