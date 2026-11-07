"""Tests for the short answer on the homepage. All data here is invented.

Numbers such as 12345 are not real fees.
"""

from datetime import date, timedelta

import pytest

from app.extensions import db
from app.logic.checklist import FEE_NOT_VERIFIED_MESSAGE
from app.logic.home import quick_tags
from app.logic.verification import create_verification_records
from app.models import (
    ProcessingInformation,
    RequiredDocument,
    SearchLog,
    ServiceFee,
    ServiceOffice,
)
from seed.presentation import seed_presentation_data


def ask(client, question):
    response = client.get("/services/quick-answer", query_string={"q": question})
    assert response.status_code == 200
    return response.get_json()


@pytest.fixture
def real(sample):
    sample.service.is_demo = False
    create_verification_records(sample.service)
    db.session.add_all([
        RequiredDocument(service=sample.service, name="Needed paper"),
        RequiredDocument(service=sample.service, name="Extra paper", is_mandatory=False),
        ServiceFee(service=sample.service, fee_name="Test fee", amount_ugx=12345,
                   payment_method="Secret method"),
        ProcessingInformation(service=sample.service, min_working_days=2, max_working_days=4,
                              basis="estimate"),
        ServiceOffice(service=sample.service, office=sample.office),
    ])
    db.session.commit()
    return sample


def verify_fees(data, review_due_on):
    for record in data.service.verification_records:
        if record.section == "fees":
            record.status = "verified"
            record.source = data.source
            record.last_checked_on = date.today()
            record.review_due_on = review_due_on
            record.verified_by = data.verifier
    db.session.commit()


def test_answer_covers_the_four_essentials(client, real):
    answer = ask(client, "example service")

    assert answer["found"] is True
    assert answer["name"] == "Example Service"
    assert answer["documents"] == "Needed paper"
    assert answer["office"] == "Example Office"
    assert answer["time"] == "2 to 4 working days (Estimate)"
    assert answer["checklist_url"] == "/services/example-service"


def test_unverified_fee_never_reaches_the_answer(client, real):
    answer = ask(client, "example service")
    response_text = str(answer)

    assert answer["fee"] == FEE_NOT_VERIFIED_MESSAGE
    assert "12345" not in response_text
    assert "12,345" not in response_text
    assert "Secret method" not in response_text


def test_verified_fee_appears_in_the_answer(client, real):
    verify_fees(real, date.today() + timedelta(days=30))
    assert ask(client, "example service")["fee"] == "UGX 12,345"


def test_demo_service_never_shows_a_fee(client, real):
    verify_fees(real, date.today() + timedelta(days=30))
    real.service.is_demo = True
    db.session.commit()

    answer = ask(client, "example service")
    assert answer["fee"] == FEE_NOT_VERIFIED_MESSAGE
    assert answer["is_demo"] is True


def test_answer_shows_the_overall_status(client, real):
    answer = ask(client, "example service")
    assert answer["status"] == "pending"
    assert answer["status_label"] == "Pending verification"


def test_empty_details_are_stated_honestly(client, sample):
    answer = ask(client, "example service")
    assert answer["documents"] == "No document list has been added yet."
    assert answer["office"] == "No offices have been listed for this service yet."
    assert answer["time"] == "Not confirmed"


def test_several_offices_are_summarised(client, real):
    from app.models import GovernmentOffice

    second = GovernmentOffice(institution=real.institution, district=real.district,
                              name="Second Office")
    db.session.add(ServiceOffice(service=real.service, office=second))
    db.session.commit()
    assert " and 1 more" in ask(client, "example service")["office"]


def test_archived_service_is_not_answered(client, real):
    real.service.is_archived = True
    db.session.commit()
    assert ask(client, "example service")["found"] is False


def test_no_match_returns_the_question(client, real):
    answer = ask(client, "zzzzzz")
    assert answer == {"found": False, "query": "zzzzzz", "suggestion": None}


def test_close_spelling_gets_a_suggestion(client, real):
    assert ask(client, "exampel")["suggestion"] == "example"


def test_empty_question_is_harmless(client, real):
    assert ask(client, "   ")["found"] is False
    assert db.session.query(SearchLog).count() == 0


def test_question_is_logged_without_personal_details(client, real):
    ask(client, "example CM12345678ABCD")
    assert db.session.query(SearchLog).one().query_text == "example"


def test_quick_tags_hide_the_long_prefix_but_ask_the_full_name(presentation_data):
    tag = quick_tags()[0]
    assert not tag["label"].startswith("Demonstration")
    assert tag["query"].startswith("Demonstration")


@pytest.fixture
def presentation_data(database):
    seed_presentation_data()


def test_everyday_words_find_a_fictional_service(client, presentation_data):
    assert ask(client, "birth")["name"] == "Demonstration Birth Record Request"
    assert ask(client, "how to get a tax number")["found"] is True
