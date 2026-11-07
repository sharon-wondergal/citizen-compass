"""Tests for the citizen report form and the presentation data.

All data here is invented for testing.
"""

import pytest

from app import create_app
from app.config import TestingConfig
from app.extensions import db
from app.logic.home import popular_services
from app.logic.verification import overall_status
from app.models import (
    CitizenReport,
    DailyView,
    District,
    GovernmentInstitution,
    GovernmentOffice,
    GovernmentService,
    OfficialSource,
    Region,
    ServiceCategory,
)
from seed.demo import remove_demo_data
from seed.presentation import EXTRA_SERVICES, seed_presentation_data

DESCRIPTION = "The example fee on this page looks wrong."


def report_values(**changes):
    values = {"problem_type": "incorrect_fee", "description": DESCRIPTION,
              "service_name": "A service I typed"}
    values.update(changes)
    return values


def send(client, **changes):
    return client.post("/report", data=report_values(**changes), follow_redirects=True)


# ---------- Reporting a problem ----------

def test_report_page_loads(client, sample):
    text = client.get("/report").get_data(as_text=True)
    assert "Report a problem" in text
    assert "Example Service" in text


def test_report_needs_no_account_and_gives_a_reference(client, sample):
    text = send(client).get_data(as_text=True)
    report = db.session.query(CitizenReport).one()

    assert report.reference_code.startswith("CC-")
    assert report.reference_code in text
    assert report.status == "new"


def test_contact_details_are_optional(client, sample):
    send(client)
    assert db.session.query(CitizenReport).one().contact_info is None


def test_report_can_name_a_listed_service(client, sample):
    send(client, service_id=sample.service.id, service_name="")
    report = db.session.query(CitizenReport).one()

    assert report.service_id == sample.service.id
    assert report.service_name == "Example Service"


def test_checklist_link_chooses_the_service(client, sample):
    text = client.get("/report?service=example-service").get_data(as_text=True)
    assert f'<option selected value="{sample.service.id}">' in text


def test_unknown_service_in_the_link_is_ignored(client, sample):
    assert client.get("/report?service=no-such-service").status_code == 200


def test_report_needs_a_service(client, sample):
    text = send(client, service_name="").get_data(as_text=True)
    assert "Choose a service or type its name." in text
    assert db.session.query(CitizenReport).count() == 0


@pytest.mark.parametrize("description", ["", "Too short", "x" * 2001])
def test_report_description_is_checked(client, sample, description):
    send(client, description=description)
    assert db.session.query(CitizenReport).count() == 0


def test_unknown_problem_type_is_refused(client, sample):
    send(client, problem_type="hacking")
    assert db.session.query(CitizenReport).count() == 0


def test_filled_hidden_field_saves_nothing_but_looks_normal(client, sample):
    text = send(client, website="http://spam.example").get_data(as_text=True)
    assert "We&#39;ve received your report" in text or "We've received your report" in text
    assert db.session.query(CitizenReport).count() == 0


def test_thanks_page_cannot_be_reloaded_without_a_report(client, sample):
    assert client.get("/report/thanks").status_code == 302


def test_report_is_never_shown_publicly(client, sample):
    send(client, service_id=sample.service.id, service_name="")
    assert DESCRIPTION not in client.get("/services/example-service").get_data(as_text=True)


def test_report_text_is_stored_as_plain_text(client, sample):
    send(client, description="<script>bad()</script> example text")
    report = db.session.query(CitizenReport).one()
    assert report.description.startswith("<script>")


def test_report_warns_against_personal_details(client, sample):
    text = client.get("/report").get_data(as_text=True)
    assert "don&#39;t include ID numbers" in text or "don't include ID numbers" in text


def test_too_many_reports_are_slowed_down(monkeypatch):
    monkeypatch.setattr(TestingConfig, "RATELIMIT_ENABLED", True)
    limited_app = create_app("testing")

    with limited_app.app_context():
        db.create_all()
    client = limited_app.test_client()
    statuses = [client.post("/report", data=report_values()).status_code for _ in range(6)]

    with limited_app.app_context():
        db.session.remove()
        db.drop_all()

    assert statuses[:5] == [302] * 5
    assert statuses[5] == 429


def test_dashboard_counts_a_new_report(client, sample):
    send(client)
    from app.logic.dashboard import build_dashboard
    assert build_dashboard()["open_reports"] == 1


# ---------- Presentation data ----------

@pytest.fixture
def presentation(database):
    seed_presentation_data()


def test_presentation_data_runs_once(database):
    assert seed_presentation_data() == len(EXTRA_SERVICES)
    assert seed_presentation_data() == 0


def test_every_presentation_record_is_clearly_fictional(presentation):
    for model in (GovernmentService, GovernmentInstitution, GovernmentOffice):
        for record in db.session.query(model):
            assert record.is_demo is True
            assert record.name.startswith("Demonstration")
    for model in (District, Region):
        for record in db.session.query(model):
            assert record.name.startswith("Demonstration")


def test_presentation_data_contains_no_invented_numbers(presentation):
    for service in db.session.query(GovernmentService):
        assert all(fee.amount_ugx is None for fee in service.fees)
        for item in service.processing:
            assert item.min_working_days is None
            assert item.max_working_days is None


def test_presentation_services_are_never_verified(presentation):
    for service in db.session.query(GovernmentService):
        assert overall_status(service) == "pending"


def test_every_presentation_checklist_has_content(client, presentation):
    for service in db.session.query(GovernmentService):
        response = client.get(f"/services/{service.slug}")
        assert response.status_code == 200
        assert service.documents
        assert service.fees


def test_popular_section_has_services_to_show(presentation):
    assert len(popular_services()) == 6


def test_every_category_has_a_service(presentation):
    used = {service.category_id for service in db.session.query(GovernmentService)}
    assert len(used) == 14


def test_most_services_have_nearby_offices(presentation):
    linked = [s for s in db.session.query(GovernmentService) if s.office_links]
    assert len(linked) >= 10


def test_removing_demo_data_clears_the_presentation_set(presentation):
    remove_demo_data()
    for model in (GovernmentService, GovernmentInstitution, GovernmentOffice, OfficialSource,
                  District, Region, DailyView):
        assert db.session.query(model).count() == 0
    assert db.session.query(ServiceCategory).count() == 14


def test_removing_demo_data_keeps_real_places(presentation):
    real_region = Region(name="Real Region")
    db.session.add_all([real_region, District(name="Real District", region=real_region)])
    db.session.commit()

    remove_demo_data()
    assert db.session.query(District).one().name == "Real District"
    assert db.session.query(Region).one().name == "Real Region"


def test_presentation_command_runs(app, database):
    result = app.test_cli_runner().invoke(args=["seed", "presentation"])
    assert result.exit_code == 0
    assert f"Added {len(EXTRA_SERVICES)} more demonstration services." in result.output
