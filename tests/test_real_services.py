"""Tests that the real services stay honest: sourced, pending and with fees hidden."""

from urllib.parse import urlsplit

import pytest

from app.extensions import db
from app.logic.checklist import FEE_NOT_VERIFIED_MESSAGE
from app.logic.home import quick_tags
from app.logic.quick_answer import find_answer
from app.logic.verification import overall_status
from app.models import (
    GovernmentInstitution,
    GovernmentOffice,
    GovernmentService,
    OfficialSource,
    ServiceFee,
    VerificationRecord,
)
from seed.demo import remove_demo_data
from seed.presentation import seed_presentation_data
from seed.real_services import SERVICES, seed_real_services

OFFICIAL_ENDINGS = (".go.ug", ".or.ug")


@pytest.fixture
def real(database):
    seed_real_services()


def page(client, slug):
    response = client.get(f"/services/{slug}")
    assert response.status_code == 200
    return response.get_data(as_text=True)


def test_seed_runs_once(database):
    assert seed_real_services() == len(SERVICES)
    assert seed_real_services() == 0


def test_real_services_are_not_marked_as_demonstrations(real):
    for service in db.session.query(GovernmentService):
        assert service.is_demo is False
        assert not service.name.startswith("Demonstration")


def test_nothing_is_verified(real):
    for service in db.session.query(GovernmentService):
        assert overall_status(service) == "pending"
    for record in db.session.query(VerificationRecord):
        assert record.status == "pending"
        assert record.verified_by is None
        assert record.last_checked_on is None
    for model in (GovernmentInstitution, GovernmentOffice):
        for item in db.session.query(model):
            assert item.verification_status == "pending"


def test_every_source_is_an_official_site(real):
    for source in db.session.query(OfficialSource):
        host = urlsplit(source.url).hostname
        assert host.endswith(OFFICIAL_ENDINGS), source.url


def test_every_service_row_cites_a_source(real):
    for service in db.session.query(GovernmentService):
        for group in (service.documents, service.fees, service.processing, service.steps):
            assert all(item.source is not None for item in group)


def test_every_section_records_how_it_was_entered(real):
    for record in db.session.query(VerificationRecord):
        assert record.source is not None
        assert "Awaiting a second person's check" in record.notes


@pytest.mark.parametrize("slug, amount", [
    ("ordinary-passport-application", "250,000"),
    ("business-name-registration", "55,000"),
    ("company-registration", "105,000"),
    ("certificate-of-good-conduct", "76,000"),
])
def test_unverified_fees_stay_hidden_from_citizens(client, real, slug, amount):
    text = page(client, slug)
    assert amount not in text
    assert FEE_NOT_VERIFIED_MESSAGE in text


def test_quick_answer_hides_real_fees_too(app, real):
    with app.test_request_context():
        answer = find_answer("passport")
    assert answer["name"] == "Ordinary Passport Application"
    assert answer["fee"] == FEE_NOT_VERIFIED_MESSAGE


def test_disputed_national_id_fee_stays_blank(real):
    fee = (
        db.session.query(ServiceFee)
        .join(GovernmentService)
        .filter(GovernmentService.slug == "replacement-of-national-id")
        .one()
    )
    assert fee.amount_ugx is None


def test_tin_has_no_invented_fee(real):
    service = db.session.query(GovernmentService).filter_by(slug="individual-tin-application").one()
    assert service.fees == []


def test_processing_times_are_only_those_stated(real):
    stated = {"certificate-of-good-conduct", "recognition-and-equation-of-qualifications"}
    for service in db.session.query(GovernmentService):
        assert bool(service.processing) == (service.slug in stated)


def test_every_real_checklist_loads(client, real):
    for details in SERVICES:
        assert "Pending verification" in page(client, details["slug"])


def test_old_police_document_list_is_flagged(real):
    service = db.session.query(GovernmentService).filter_by(slug="certificate-of-good-conduct").one()
    record = next(r for r in service.verification_records if r.section == "documents")
    assert "22 October 2018" in record.notes
    assert record.source.published_on.year == 2018


def test_passport_minor_gets_different_documents(client, real):
    service = db.session.query(GovernmentService).filter_by(slug="ordinary-passport-application").one()
    minor = next(variant for variant in service.variants if variant.name == "Minor")
    text = client.get(f"/services/{service.slug}?variant={minor.id}").get_data(as_text=True)

    assert "Parental consent letter" in text
    assert "Recommendation letter" not in text


def test_everyday_national_id_name_is_searchable(client, real):
    assert "Replacement of National ID" in client.get("/services?q=ndaga").get_data(as_text=True)


def test_real_services_come_first_in_quick_tags(database):
    seed_presentation_data()
    seed_real_services()
    assert all(tag["is_demo"] is False for tag in quick_tags())


def test_real_services_beat_fictional_ones_on_a_tie(app, database):
    seed_presentation_data()
    seed_real_services()
    with app.test_request_context():
        assert find_answer("passport")["is_demo"] is False


def test_removing_demo_data_keeps_real_services(database):
    seed_presentation_data()
    seed_real_services()
    remove_demo_data()

    assert db.session.query(GovernmentService).count() == len(SERVICES)
    assert db.session.query(GovernmentInstitution).count() == 6


def test_command_runs(app, database):
    result = app.test_cli_runner().invoke(args=["seed", "real"])
    assert result.exit_code == 0
    assert f"Added {len(SERVICES)} real services." in result.output
