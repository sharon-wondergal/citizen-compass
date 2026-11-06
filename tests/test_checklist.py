"""Stage 8 tests: the six-field citizen preparation checklist.

All data here is invented for testing. Numbers such as 12345 are not real fees.
"""

from datetime import date, timedelta

import pytest

from app.extensions import db
from app.logic.analytics import record_service_view
from app.logic.checklist import (
    FEE_NOT_VERIFIED_MESSAGE,
    build_checklist,
    choose_variant,
    describe_duration,
    get_service,
    list_offices,
    overall_last_checked,
)
from app.logic.verification import create_verification_records, overall_status
from app.models import (
    DailyView,
    District,
    GovernmentOffice,
    OfficialSource,
    ProcessingInformation,
    Region,
    RequiredDocument,
    ServiceFee,
    ServiceOffice,
    ServiceStep,
    ServiceVariant,
)
from app.template_helpers import long_date, ugx
from seed.demo import seed_demo_data

ADDRESS = "/services/example-service"
FUTURE = date.today() + timedelta(days=90)
PAST = date.today() - timedelta(days=1)


def page(client, address=ADDRESS):
    response = client.get(address)
    assert response.status_code == 200
    return response.get_data(as_text=True)


@pytest.fixture
def real(sample):
    """The sample service, treated as a real record with pending sections."""
    sample.service.is_demo = False
    create_verification_records(sample.service)
    db.session.commit()
    return sample


def verify(data, section, review_due_on=FUTURE):
    for record in data.service.verification_records:
        if record.section == section:
            record.status = "verified"
            record.source = data.source
            record.last_checked_on = date.today() - timedelta(days=5)
            record.review_due_on = review_due_on
            record.verified_by = data.verifier
    db.session.commit()


def add_fee(data, **values):
    fee = ServiceFee(service=data.service, fee_name="Test fee", **values)
    db.session.add(fee)
    db.session.commit()
    return fee


# ---------- Finding the page ----------

def test_checklist_page_loads(client, real):
    text = page(client)
    assert "Example Service" in text
    assert "Example Agency" in text


def test_all_six_fields_are_present(client, real):
    text = page(client)
    for heading in ["Service information", "Required documents", "Official service fees",
                    "Government office locations", "Processing time",
                    "Official sources and verification"]:
        assert heading in text


def test_unknown_service_returns_404(client, database):
    assert client.get("/services/no-such-service").status_code == 404


def test_archived_service_returns_404(client, real):
    real.service.is_archived = True
    db.session.commit()
    assert client.get(ADDRESS).status_code == 404


def test_search_results_link_to_the_checklist(client, real):
    assert f'href="{ADDRESS}"' in page(client, "/services")


# ---------- Field 1: service information ----------

def test_unconfirmed_information_says_so(client, real):
    text = page(client)
    assert "Who qualifies" in text
    assert text.count("Not confirmed") >= 2


def test_steps_appear_in_order(client, real):
    db.session.add_all([
        ServiceStep(service=real.service, step_number=2, title="Second action"),
        ServiceStep(service=real.service, step_number=1, title="First action"),
    ])
    db.session.commit()
    text = page(client)
    assert text.index("First action") < text.index("Second action")


# ---------- Field 2: documents ----------

def test_required_and_optional_documents_are_separated(client, real):
    db.session.add_all([
        RequiredDocument(service=real.service, name="Needed paper"),
        RequiredDocument(service=real.service, name="Extra paper", is_mandatory=False),
    ])
    db.session.commit()
    text = page(client)
    assert text.index("You must bring") < text.index("Needed paper")
    assert text.index("You may also need") < text.index("Extra paper")


def test_only_required_documents_count_towards_progress(client, real):
    needed = RequiredDocument(service=real.service, name="Needed paper")
    extra = RequiredDocument(service=real.service, name="Extra paper", is_mandatory=False)
    db.session.add_all([needed, extra])
    db.session.commit()
    text = page(client)
    assert text.count("data-required") == 1


def test_document_details_are_shown(client, real):
    db.session.add(RequiredDocument(
        service=real.service, name="Paper", original_required=True, photocopies=2,
        certified_copy_accepted=False, max_age_days=21, instructions="Bring it folded.",
    ))
    db.session.commit()
    text = page(client)
    assert "Required" in text
    assert "Not accepted" in text
    assert "21 days" in text
    assert "Bring it folded." in text


def test_zero_photocopies_differs_from_unconfirmed(real):
    document = RequiredDocument(service=real.service, name="Paper", photocopies=0)
    db.session.add(document)
    db.session.commit()
    assert build_checklist(real.service)["documents"][0]["photocopies"] == 0


def test_missing_document_details_are_not_guessed(real):
    db.session.add(RequiredDocument(service=real.service, name="Paper"))
    db.session.commit()
    document = build_checklist(real.service)["documents"][0]
    assert document["original"] == "Not confirmed"
    assert document["photocopies"] == "Not confirmed"
    assert document["certified_copy"] == "Not confirmed"


def test_no_documents_gives_an_honest_message(client, real):
    assert "No document list has been added yet." in page(client)


# ---------- Field 3: fees ----------

def test_pending_fee_amount_never_reaches_the_page(client, real):
    add_fee(real, amount_ugx=12345, payment_method="Secret method",
            payment_instructions="Secret instructions")
    text = page(client)

    assert FEE_NOT_VERIFIED_MESSAGE in text
    assert "12,345" not in text
    assert "12345" not in text
    assert "Secret method" not in text
    assert "Secret instructions" not in text


def test_verified_fee_shows_its_amount(client, real):
    add_fee(real, amount_ugx=12345, payment_method="Bank")
    verify(real, "fees")
    text = page(client)

    assert "UGX 12,345" in text
    assert "Payment method: Bank" in text
    assert FEE_NOT_VERIFIED_MESSAGE not in text


def test_verified_section_with_unknown_amount_shows_the_message(client, real):
    add_fee(real, amount_ugx=None)
    verify(real, "fees")
    assert FEE_NOT_VERIFIED_MESSAGE in page(client)


def test_verified_free_service_says_free(client, real):
    add_fee(real, amount_ugx=0)
    verify(real, "fees")
    assert "<strong>Free</strong>" in page(client)


def test_outdated_fee_shows_the_amount_with_a_warning(client, real):
    add_fee(real, amount_ugx=12345)
    verify(real, "fees", review_due_on=PAST)
    text = page(client)

    assert "UGX 12,345" in text
    assert "past its review date" in text


@pytest.mark.parametrize("status", ["pending", "unavailable"])
def test_unverified_statuses_hide_the_amount(real, status):
    add_fee(real, amount_ugx=12345)
    for record in real.service.verification_records:
        if record.section == "fees":
            record.status = status
    db.session.commit()
    assert build_checklist(real.service)["fees"][0]["amount_ugx"] is None


def test_demo_service_never_shows_an_amount(client, real):
    """Even a record wrongly set to verified can't show a demonstration fee."""
    add_fee(real, amount_ugx=12345)
    verify(real, "fees")
    real.service.is_demo = True
    db.session.commit()
    text = page(client)

    assert "12,345" not in text
    assert FEE_NOT_VERIFIED_MESSAGE in text


def test_no_fee_rows_shows_the_message(client, real):
    assert FEE_NOT_VERIFIED_MESSAGE in page(client)


def test_ordinary_and_express_are_labelled(client, real):
    add_fee(real, service_speed="ordinary", amount_ugx=100)
    add_fee(real, service_speed="express", amount_ugx=200)
    verify(real, "fees")
    text = page(client)
    assert "(Ordinary)" in text
    assert "(Express)" in text


# ---------- Field 4: offices ----------

@pytest.fixture
def places(real):
    """Offices in three places, including a Kampala-style headquarters."""
    second_region = Region(name="Other Region")
    near = real.district
    same_region = District(name="Same Region District", region=real.region)
    far = District(name="Far District", region=second_region)

    offices = {
        "near": real.office,
        "same_region": GovernmentOffice(
            institution=real.institution, district=same_region, name="Same Region Office"
        ),
        "far": GovernmentOffice(
            institution=real.institution, district=far, name="Far Office"
        ),
        "headquarters": GovernmentOffice(
            institution=real.institution, district=far, name="Aaa Headquarters",
            office_type="headquarters",
        ),
    }
    for office in offices.values():
        db.session.add(ServiceOffice(service=real.service, office=office))
    db.session.commit()
    real.offices = offices
    real.near = near
    real.far_region = second_region
    return real


def office_names(entries):
    return [entry["office"].name for entry in entries]


def test_local_offices_come_before_headquarters(places):
    names = office_names(list_offices(places.service))
    assert names[-1] == "Aaa Headquarters"


def test_chosen_district_comes_first_then_its_region(places):
    entries = list_offices(places.service, district=places.near)
    assert entries[0]["office"].name == "Example Office"
    assert entries[0]["nearness"] == "district"
    assert entries[1]["office"].name == "Same Region Office"
    assert entries[1]["nearness"] == "region"
    assert entries[2]["nearness"] == "other"


def test_chosen_region_comes_first(places):
    entries = list_offices(places.service, region_id=places.far_region.id)
    assert {entry["nearness"] for entry in entries[:2]} == {"region"}


def test_office_page_filter_labels_nearby_offices(client, places):
    text = page(client, f"{ADDRESS}?district={places.near.id}")
    assert "In your district" in text
    assert "In your region" in text


def test_no_nearby_office_is_stated_honestly(client, places):
    lonely = Region(name="Lonely Region")
    db.session.add(lonely)
    db.session.commit()
    text = page(client, f"{ADDRESS}?region={lonely.id}")
    assert "We haven't listed an office for this service near the place you chose." in text


def test_archived_office_is_hidden(client, places):
    places.offices["far"].is_archived = True
    db.session.commit()
    assert "Far Office" not in page(client)


def test_missing_office_details_are_not_invented(client, places):
    text = page(client)
    assert "Address not yet verified" in text
    assert "tel:" not in text


def test_pending_office_link_is_labelled(client, places):
    text = page(client)
    assert "Offers this service:" in text
    assert "status-badge status-pending" in text


def test_invalid_location_values_are_ignored(client, places):
    assert "Example Office" in page(client, f"{ADDRESS}?district=abc&region=999999")


def test_no_offices_gives_an_honest_message(client, real):
    assert "No offices have been listed for this service yet." in page(client)


# ---------- Field 5: processing ----------

@pytest.mark.parametrize("low, high, expected", [
    (None, None, "Not confirmed"),
    (5, 10, "5 to 10 working days"),
    (5, 5, "5 working days"),
    (1, 1, "1 working day"),
    (None, 10, "Up to 10 working days"),
    (5, None, "At least 5 working days"),
])
def test_duration_wording(low, high, expected):
    item = ProcessingInformation(min_working_days=low, max_working_days=high)
    assert describe_duration(item) == expected


def test_official_and_estimated_times_are_distinguished(client, real):
    db.session.add_all([
        ProcessingInformation(service=real.service, basis="official_standard",
                              starts_after="payment", service_speed="ordinary"),
        ProcessingInformation(service=real.service, basis="estimate", service_speed="express"),
    ])
    db.session.commit()
    text = page(client)
    assert "Official standard" in text
    assert "Estimate" in text
    assert "Counted from payment" in text


# ---------- Field 6: sources and verification ----------

def test_every_section_status_is_listed(client, real):
    text = page(client)
    assert text.count("Not yet checked") >= 5


def test_sources_are_clickable_and_listed_once(client, real):
    db.session.add_all([
        RequiredDocument(service=real.service, name="Paper", source=real.source),
        ServiceFee(service=real.service, fee_name="Fee", source=real.source),
    ])
    db.session.commit()
    text = page(client)

    assert text.count('href="https://example.test/source"') == 1
    assert 'rel="noopener noreferrer"' in text


def test_source_of_a_hidden_fee_is_still_listed(real):
    add_fee(real, source=real.source, amount_ugx=12345)
    assert real.source in build_checklist(real.service)["sources"]


def test_verifier_names_stay_out_of_the_public_page(client, real):
    verify(real, "fees")
    assert "Example Verifier" not in page(client)


def test_review_dates_are_visible(client, real):
    verify(real, "fees")
    assert f"Next review: {long_date(FUTURE)}" in page(client)


def test_overall_date_needs_every_section_checked():
    sections = {"a": {"last_checked_on": date(2026, 1, 1)}, "b": {"last_checked_on": None}}
    assert overall_last_checked(sections) is None


def test_overall_date_is_the_oldest_check():
    sections = {
        "a": {"last_checked_on": date(2026, 1, 1)},
        "b": {"last_checked_on": date(2026, 3, 1)},
    }
    assert overall_last_checked(sections) == date(2026, 1, 1)


def test_one_pending_section_keeps_the_page_pending(real):
    verify(real, "fees")
    checklist = build_checklist(real.service)
    assert checklist["sections"]["fees"]["status"] == "verified"
    assert checklist["status"] == "pending"


def test_fully_verified_real_service_shows_verified(real):
    for record in list(real.service.verification_records):
        verify(real, record.section)
    assert overall_status(real.service) == "verified"


# ---------- Variants ----------

@pytest.fixture
def variants(real):
    damaged = ServiceVariant(service=real.service, name="Damaged", is_default=True)
    lost = ServiceVariant(service=real.service, name="Lost")
    db.session.add_all([
        damaged,
        lost,
        RequiredDocument(service=real.service, name="Shared paper"),
        RequiredDocument(service=real.service, variant=damaged, name="Broken item"),
        RequiredDocument(service=real.service, variant=lost, name="Police paper"),
    ])
    db.session.commit()
    real.damaged = damaged
    real.lost = lost
    return real


def test_default_variant_is_used_first(client, variants):
    text = page(client)
    assert "Broken item" in text
    assert "Police paper" not in text
    assert "Shared paper" in text


def test_choosing_a_variant_changes_the_documents(client, variants):
    text = page(client, f"{ADDRESS}?variant={variants.lost.id}")
    assert "Police paper" in text
    assert "Broken item" not in text
    assert "Shared paper" in text


@pytest.mark.parametrize("value", ["abc", "999999"])
def test_invalid_variant_falls_back_to_the_default(client, variants, value):
    assert "Broken item" in page(client, f"{ADDRESS}?variant={value}")


def test_another_services_variant_is_not_accepted(variants):
    assert choose_variant(variants.service, -1) is variants.damaged


def test_first_variant_is_used_when_none_is_default(variants):
    variants.damaged.is_default = False
    db.session.commit()
    assert choose_variant(get_service("example-service")) is not None


def test_each_variant_keeps_separate_ticks(client, variants):
    first = page(client)
    second = page(client, f"{ADDRESS}?variant={variants.lost.id}")
    key = f'cc-checklist-{variants.service.id}-'
    assert f'{key}{variants.damaged.id}"' in first
    assert f'{key}{variants.lost.id}"' in second


# ---------- Interactive features and safety ----------

def test_buttons_needing_javascript_start_hidden(client, real):
    text = page(client)
    assert "data-print-button hidden" in text
    assert "data-share-button hidden" in text
    assert "js/checklist.js" in text


def test_agency_website_appears_only_when_known(client, real):
    assert "Agency website" not in page(client)
    real.institution.website = "https://example.test/agency"
    db.session.commit()
    assert 'href="https://example.test/agency"' in page(client)


def test_report_link_waits_for_the_report_feature(client, real):
    assert "Report incorrect information" not in page(client)


def test_page_data_is_escaped(client, real):
    db.session.add(RequiredDocument(service=real.service, name="<script>bad()</script>"))
    db.session.commit()
    text = page(client)
    assert "<script>bad()</script>" not in text
    assert "&lt;script&gt;" in text


def test_printed_copy_says_it_is_not_official(client, real):
    """The site header is hidden on paper, so the print notice must say this."""
    text = page(client)
    start = text.index('<p class="print-only">')
    notice = text[start:text.index("</p>", start)]

    assert "Printed from Citizen Compass on" in notice
    assert "not a government website" in notice
    assert "isn't an official document" in notice


# ---------- Demonstration data ----------

def test_demo_page_carries_a_clear_warning(client, database):
    seed_demo_data()
    text = page(client, "/services/demonstration-identity-card-replacement")
    assert "Demonstration only." in text
    assert "isn't a real government requirement" in text
    assert "Demonstration source (not a real official page)" in text


def test_demo_source_cannot_be_a_real_agency_page(database):
    seed_demo_data()
    source = db.session.query(OfficialSource).one()
    assert source.url.startswith("https://example.org/")


# ---------- View counts ----------

def test_opening_a_checklist_counts_a_view(client, real):
    page(client)
    page(client)
    view = db.session.query(DailyView).one()
    assert view.view_count == 2
    assert view.service_id == real.service.id


def test_each_day_gets_its_own_count(real):
    record_service_view(real.service.id, date(2026, 1, 1))
    record_service_view(real.service.id, date(2026, 1, 2))
    assert db.session.query(DailyView).count() == 2


def test_missing_page_is_not_counted(client, database):
    client.get("/services/no-such-service")
    assert db.session.query(DailyView).count() == 0


def test_view_count_failure_does_not_stop_the_page(client, real, monkeypatch):
    from sqlalchemy.exc import OperationalError

    def broken_commit():
        raise OperationalError("UPDATE", {}, Exception("database is locked"))

    monkeypatch.setattr(db.session, "commit", broken_commit)
    assert "Example Service" in page(client)


def test_viewed_service_reaches_popular_on_the_homepage(client, real):
    page(client)
    assert 'href="/services/example-service"' in page(client, "/")


# ---------- Formatting ----------

def test_date_format():
    assert long_date(date(2026, 11, 6)) == "6 November 2026"


def test_money_format():
    assert ugx(1250000) == "UGX 1,250,000"
    assert ugx(0) == "Free"
