"""Reviewing citizen reports, and analytics."""

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.blueprints.admin import admin_bp
from app.extensions import db
from app.forms.report_review import ReportReviewForm
from app.logic.insights import build_insights
from app.logic.report_review import REPORT_STATUS_LABELS, list_reports, update_report
from app.logic.reports import PROBLEM_LABELS
from app.models import CitizenReport

FILTERS = {"open": "Open", **REPORT_STATUS_LABELS, "all": "All"}


@admin_bp.context_processor
def report_labels():
    return {"report_status_labels": REPORT_STATUS_LABELS, "problem_labels": PROBLEM_LABELS}


@admin_bp.route("/reports")
@login_required
def reports():
    status_filter = request.args.get("status", "open")
    if status_filter not in FILTERS:
        status_filter = "open"
    page = max(request.args.get("page", default=1, type=int) or 1, 1)
    return render_template(
        "admin/reports.html",
        results=list_reports(status_filter, page),
        status_filter=status_filter,
        filters=FILTERS,
    )


@admin_bp.route("/reports/<int:report_id>", methods=["GET", "POST"])
@login_required
def report_detail(report_id):
    report = db.session.get(CitizenReport, report_id)
    if report is None:
        abort(404)

    form = ReportReviewForm(data={"status": report.status, "action_taken": report.action_taken})
    if form.validate_on_submit():
        update_report(report, current_user, form.status.data, form.action_taken.data)
        flash(f"Report {report.reference_code} was updated.", "success")
        return redirect(url_for("admin.reports"))

    return render_template("admin/report_detail.html", report=report, form=form)


@admin_bp.route("/analytics")
@login_required
def analytics():
    return render_template("admin/analytics.html", insights=build_insights())
