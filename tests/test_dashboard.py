"""Stage 10 tests: the administrator dashboard. All data here is invented."""

from datetime import date, timedelta

import pytest

from app.extensions import db
from app.logic.auth import create_admin
from app.logic.dashboard import bar_rows, build_dashboard
from app.logic.verification import create_verification_records
from app.models import CitizenReport, GovernmentService, ServiceCategory

PASSWORD = "correct-horse-battery"


@pytest.fixture
def signed_in(client, database):
    create_admin("Dashboard Tester", "tester@example.com", PASSWORD, "verifier")
    client.post("/admin/login", data={"email": "tester@example.com", "password": PASSWORD})
    return client


def page(client):
    response = client.get("/admin")
    assert response.status_code == 200
    return response.get_data(as_text=True)


def verify_all(data, service, review_due_on):
    service.is_demo = False
    create_verification_records(service)
    for record in service.verification_records:
        record.status = "verified"
        record.source = data.source
        record.last_checked_on = date.today() - timedelta(days=5)
        record.review_due_on = review_due_on
        record.verified_by = data.verifier
    db.session.commit()


def add_report(code, status="new", **values):
    report = CitizenReport(
        reference_code=code, service_name="Example", problem_type="other",
        description="An example problem report.", status=status, **values,
    )
    db.session.add(report)
    db.session.commit()


def test_empty_dashboard_is_honest(signed_in):
    text = page(signed_in)
    assert "No services have been added yet." in text
    assert "No records have been added yet." in text


def test_dashboard_names_the_signed_in_admin(signed_in):
    text = page(signed_in)
    assert "Dashboard Tester" in text
    assert "Verifier" in text


def test_dashboard_never_shows_password_hashes(signed_in):
    assert "scrypt:" not in page(signed_in)


def test_totals_count_open_records_only(sample):
    assert build_dashboard()["total_services"] == 1
    sample.service.is_archived = True
    sample.office.is_archived = True
    db.session.commit()

    dashboard = build_dashboard()
    assert dashboard["total_services"] == 0
    assert dashboard["total_offices"] == 0
    assert dashboard["total_institutions"] == 1


def test_new_service_counts_as_awaiting_verification(sample):
    dashboard = build_dashboard()
    assert dashboard["pending_services"] == 1
    assert dashboard["verified_services"] == 0


def test_verified_service_is_counted(sample):
    verify_all(sample, sample.service, date.today() + timedelta(days=30))
    assert build_dashboard()["verified_services"] == 1


def test_expired_service_counts_as_outdated(sample):
    verify_all(sample, sample.service, date.today() - timedelta(days=1))
    dashboard = build_dashboard()
    assert dashboard["outdated_services"] == 1
    assert dashboard["verified_services"] == 0


def test_only_open_reports_are_counted(sample):
    add_report("CC-1")
    add_report("CC-2", "investigating")
    add_report("CC-3", "resolved", action_taken="Fixed", resolved_by=sample.verifier,
               resolved_at=date.today())
    assert build_dashboard()["open_reports"] == 2


def test_status_rows_cover_all_four_labels(sample):
    rows = build_dashboard()["status_rows"]
    assert [row["status"] for row in rows] == ["verified", "pending", "outdated", "unavailable"]
    assert sum(row["count"] for row in rows) == 1


def test_status_percent_is_a_share_of_all_services(sample):
    rows = {row["status"]: row for row in build_dashboard()["status_rows"]}
    assert rows["pending"]["percent"] == 100
    assert rows["verified"]["percent"] == 0


def test_categories_are_sorted_with_scaled_bars():
    rows = bar_rows({"Small": 1, "Large": 4})
    assert [row["label"] for row in rows] == ["Large", "Small"]
    assert rows[0]["percent"] == 100
    assert rows[1]["percent"] == 25


def test_no_data_gives_empty_bars():
    assert bar_rows({}) == []


def test_category_chart_counts_services(sample):
    second = ServiceCategory(name="Second Category", slug="second")
    db.session.add(GovernmentService(
        institution=sample.institution, category=second, name="Another",
        slug="another", summary="Example only",
    ))
    db.session.commit()
    labels = {row["label"]: row["count"] for row in build_dashboard()["category_rows"]}
    assert labels == {"Example Category": 1, "Second Category": 1}


def test_charts_are_readable_as_tables(signed_in, sample):
    text = page(signed_in)
    assert "<table" in text
    assert "<caption" in text
    assert "Pending verification" in text


def test_recent_records_are_listed(signed_in, sample):
    text = page(signed_in)
    assert "Recently updated records" in text
    assert "Example Service" in text


def test_dashboard_text_is_escaped(signed_in, sample):
    sample.service.name = "<script>bad()</script>"
    db.session.commit()
    text = page(signed_in)
    assert "<script>bad()</script>" not in text
    assert "&lt;script&gt;" in text
