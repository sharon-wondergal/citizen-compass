"""Citizens reporting incorrect information."""

from flask import Blueprint, redirect, render_template, request, session, url_for

from app.extensions import limiter
from app.forms.report import ReportForm
from app.logic.reports import create_report, find_service_id

reports_bp = Blueprint("reports", __name__)


@reports_bp.route("/report", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def new():
    form = ReportForm()
    form.load_choices()

    if request.method == "GET" and request.args.get("service"):
        form.service_id.data = find_service_id(request.args["service"])

    if form.validate_on_submit():
        # A filled hidden field means an automated tool. It sees the normal
        # thank-you page, but nothing is saved.
        if form.website.data:
            session["report_reference"] = "received"
            return redirect(url_for("reports.thanks"))

        session["report_reference"] = create_report(
            form.service_id.data,
            form.service_name.data,
            form.problem_type.data,
            form.description.data,
            form.contact_info.data,
        )
        return redirect(url_for("reports.thanks"))

    return render_template("reports/new.html", form=form)


@reports_bp.route("/report/thanks")
def thanks():
    reference = session.pop("report_reference", None)
    if reference is None:
        return redirect(url_for("reports.new"))
    return render_template("reports/thanks.html", reference=reference)
