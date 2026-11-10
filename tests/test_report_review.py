"""Stage 12 tests: reviewing citizen reports, privacy cleanup and analytics.

All data here is invented.
"""

from datetime import date, datetime, timedelta

import pytest

from app.extensions import db
from app.logic.auth import create_admin, utc_now
from app.logic.insights import build_insights
from app.logic.report_review import remove_old_personal_data
from app.models import AuditLog, CitizenReport, DailyView, SearchLog

PASSWORD = "correct-horse-battery"


@pytest.fixture
def admin_client(client, sample):
    create_admin("Report Handler", "handler@example.com", PASSWORD, "editor")
    client.post("/admin/login", data={"email": "handler@example.com", "password": PASSWORD})
    return client


def add_report(code="CC-0001", **values):
    report = CitizenReport(
        reference_code=code,
        service_name=values.pop("service_name", "Example Service"),
        problem_type=values.pop("problem_type", "incorrect_fee"),
        description=values.pop("description", "The example fee looks wrong."),
        **values,
    )
    db.session.add(report)
    db.session.commit()
    return report


# ---------- Reviewing reports ----------

def test_reports_need_login(client, sample):
    assert client.get("/admin/reports").status_code == 302


def test_open_reports_are_listed(admin_client, sample):
    add_report("CC-0001")
    add_report("CC-0002", status="investigating")
    text = admin_client.get("/admin/reports").get_data(as_text=True)
    assert "2 reports" in text
    assert "CC-0001" in text


def test_closed_reports_are_filtered_out_of_open(admin_client, sample):
    add_report("CC-0003", status="dismissed", action_taken="Checked", resolved_by=sample.editor,
               resolved_at=datetime(2026, 1, 1))
    assert "0 reports" in admin_client.get("/admin/reports").get_data(as_text=True)
    assert "CC-0003" in admin_client.get("/admin/reports?status=all").get_data(as_text=True)


def test_unknown_filter_falls_back_to_open(admin_client, sample):
    assert admin_client.get("/admin/reports?status=hack").status_code == 200


def test_report_detail_shows_contact_to_admins_only(admin_client, client, sample):
    report = add_report(contact_info="0700 000000")
    text = admin_client.get(f"/admin/reports/{report.id}").get_data(as_text=True)
    assert "0700 000000" in text
    assert "0700 000000" not in client.get("/").get_data(as_text=True)


def test_report_text_is_escaped(admin_client, sample):
    report = add_report(description="<script>bad()</script> example")
    text = admin_client.get(f"/admin/reports/{report.id}").get_data(as_text=True)
    assert "<script>bad()</script>" not in text


def test_closing_needs_the_action_taken(admin_client, sample):
    report = add_report()
    text = admin_client.post(
        f"/admin/reports/{report.id}", data={"status": "resolved", "action_taken": ""}
    ).get_data(as_text=True)
    assert "before closing" in text
    db.session.expire_all()
    assert report.status == "new"


def test_resolving_records_who_and_when(admin_client, sample):
    report = add_report()
    admin_client.post(
        f"/admin/reports/{report.id}",
        data={"status": "resolved", "action_taken": "Checked the source and corrected the fee."},
    )
    db.session.expire_all()
    entry = db.session.query(AuditLog).filter_by(action="resolve_report").one()

    assert report.status == "resolved"
    assert report.resolved_by.full_name == "Report Handler"
    assert report.resolved_at is not None
    assert entry.record_label == report.reference_code


def test_reopening_clears_the_resolution(admin_client, sample):
    report = add_report()
    address = f"/admin/reports/{report.id}"
    admin_client.post(address, data={"status": "resolved", "action_taken": "Done"})
    admin_client.post(address, data={"status": "investigating", "action_taken": "Done"})
    db.session.expire_all()

    assert report.status == "investigating"
    assert report.resolved_by is None
    assert report.resolved_at is None


def test_resolving_does_not_change_public_information(admin_client, client, sample):
    report = add_report(service=sample.service)
    admin_client.post(f"/admin/reports/{report.id}", data={"status": "resolved", "action_taken": "x"})
    db.session.expire_all()
    assert sample.service.summary == "Example only"


def test_unknown_report_returns_404(admin_client, sample):
    assert admin_client.get("/admin/reports/99999").status_code == 404


# ---------- Privacy cleanup ----------

def test_old_closed_contacts_are_blanked(sample):
    now = utc_now()
    old = add_report("CC-0001", status="resolved", action_taken="x", resolved_by=sample.editor,
                     resolved_at=now - timedelta(days=91), contact_info="old contact")
    recent = add_report("CC-0002", status="resolved", action_taken="x", resolved_by=sample.editor,
                        resolved_at=now - timedelta(days=10), contact_info="recent contact")
    still_open = add_report("CC-0003", contact_info="open contact")

    assert remove_old_personal_data(now) == (1, 0)
    assert old.contact_info is None
    assert recent.contact_info == "recent contact"
    assert still_open.contact_info == "open contact"


def test_old_searches_are_deleted(sample):
    now = utc_now()
    db.session.add_all([
        SearchLog(query_text="old", results_count=0, searched_at=now - timedelta(days=400)),
        SearchLog(query_text="new", results_count=0, searched_at=now - timedelta(days=5)),
    ])
    db.session.commit()

    assert remove_old_personal_data(now) == (0, 1)
    assert [log.query_text for log in db.session.query(SearchLog)] == ["new"]


def test_cleanup_command_runs(app, database):
    result = app.test_cli_runner().invoke(args=["privacy-cleanup"])
    assert result.exit_code == 0
    assert "Blanked 0 contact details." in result.output


# ---------- Analytics ----------

def test_analytics_needs_login(client, sample):
    assert client.get("/admin/analytics").status_code == 302


def test_empty_analytics_are_honest(admin_client, sample):
    text = admin_client.get("/admin/analytics").get_data(as_text=True)
    assert "No searches yet." in text
    assert "Nothing is outdated." in text


def test_analytics_count_searches_views_and_reports(admin_client, sample):
    db.session.add_all([
        SearchLog(query_text="passport", results_count=1),
        SearchLog(query_text="passport", results_count=1),
        SearchLog(query_text="zzzz", results_count=0),
        DailyView(view_date=date.today(), service_id=sample.service.id, view_count=7),
        DailyView(view_date=date.today(), institution_id=sample.institution.id, view_count=3),
    ])
    db.session.commit()
    add_report("CC-0001", problem_type="missing_document")

    insights = build_insights()
    assert insights["searched"][0] == {"label": "passport", "count": 2, "percent": 100}
    assert [row["label"] for row in insights["failed_searches"]] == ["zzzz"]
    assert insights["viewed"][0]["count"] == 7
    assert insights["institutions"][0]["label"] == "Example Agency"
    assert insights["problems"][0]["label"] == "Missing document"
    assert "Example Service" in admin_client.get("/admin/analytics").get_data(as_text=True)


def test_old_activity_is_left_out(sample):
    db.session.add(DailyView(view_date=date.today() - timedelta(days=60),
                             service_id=sample.service.id, view_count=9))
    db.session.commit()
    assert build_insights()["viewed"] == []


def test_outdated_services_are_listed(sample):
    from app.logic.verification import create_verification_records

    sample.service.is_demo = False
    create_verification_records(sample.service)
    for record in sample.service.verification_records:
        record.status = "verified"
        record.source = sample.source
        record.last_checked_on = date.today() - timedelta(days=200)
        record.review_due_on = date.today() - timedelta(days=1)
        record.verified_by = sample.verifier
    db.session.commit()
    assert [service.name for service in build_insights()["outdated"]] == ["Example Service"]
