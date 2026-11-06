"""Stage 7 tests: the service directory, search, filters and privacy."""

from datetime import date, timedelta

import pytest

from app import create_app
from app.config import TestingConfig
from app.extensions import db
from app.logic.search import (
    RESULTS_PER_PAGE,
    clean_query,
    remove_sensitive_text,
    search_words,
    spelling_suggestion,
    suggest_services,
)
from app.logic.verification import create_verification_records
from app.models import (
    District,
    GovernmentInstitution,
    GovernmentOffice,
    GovernmentService,
    Region,
    SearchLog,
    ServiceCategory,
)
from seed.demo import DEMO_SERVICES, remove_demo_data, seed_demo_data


def text_of(client, address):
    response = client.get(address)
    assert response.status_code == 200
    return response.get_data(as_text=True)


def add_service(sample, name, **values):
    service = GovernmentService(
        institution=values.pop("institution", sample.institution),
        category=values.pop("category", sample.category),
        name=name,
        slug=name.lower().replace(" ", "-"),
        summary=values.pop("summary", "Example only"),
        **values,
    )
    db.session.add(service)
    db.session.commit()
    return service


@pytest.fixture
def demo(database):
    seed_demo_data()


# ---------- Browsing and text search ----------

def test_directory_lists_services(client, demo):
    text = text_of(client, "/services")
    assert "3 services found" in text
    assert "Demonstration Business Name Filing" in text


def test_search_by_service_name(client, demo):
    text = text_of(client, "/services?q=travel")
    assert "1 service found" in text
    assert "Demonstration Travel Document Renewal" in text


def test_search_is_not_case_sensitive(client, demo):
    assert "1 service found" in text_of(client, "/services?q=TRAVEL")


def test_search_by_agency_name(client, demo):
    assert "2 services found" in text_of(client, "/services?q=registration+agency")


def test_search_by_acronym(client, demo):
    assert "1 service found" in text_of(client, "/services?q=DEMO-LIC")


def test_search_by_keyword(client, demo):
    text = text_of(client, "/services?q=trading")
    assert "Demonstration Business Name Filing" in text


def test_search_by_category_name(client, demo):
    text = text_of(client, "/services?q=passports")
    assert "Demonstration Travel Document Renewal" in text


def test_natural_question_still_matches(client, demo):
    assert "1 service found" in text_of(client, "/services?q=how+to+get+a+travel+document")


def test_every_word_must_match(client, demo):
    assert "0 services found" in text_of(client, "/services?q=travel+company")


def test_name_matches_rank_above_other_matches(client, sample):
    add_service(sample, "Aardvark Service", keywords="certificate")
    add_service(sample, "Zebra Certificate")
    text = text_of(client, "/services?q=certificate")
    assert text.index("Zebra Certificate") < text.index("Aardvark Service")


def test_archived_service_is_hidden(client, sample):
    sample.service.is_archived = True
    db.session.commit()
    assert "Example Service" not in text_of(client, "/services")


def test_demo_results_are_labelled(client, demo):
    assert "Demonstration only" in text_of(client, "/services")


def test_results_show_pending_status(client, demo):
    assert "status-badge status-pending" in text_of(client, "/services")


def test_unconfirmed_delivery_mode_says_so(client, sample):
    assert "Not confirmed" in text_of(client, "/services")


# ---------- Filters ----------

def test_filter_by_category(client, demo):
    text = text_of(client, "/services?category=business-registration")
    assert "1 service found" in text
    assert "Demonstration Business Name Filing" in text


def test_filter_by_institution(client, demo):
    address = "/services?institution=demonstration-registration-agency"
    assert "2 services found" in text_of(client, address)


def test_filter_by_mode(client, demo):
    assert "1 service found" in text_of(client, "/services?mode=hybrid")


def test_filter_by_district(client, demo):
    south = db.session.query(District).filter_by(name="Demonstration District South").one()
    text = text_of(client, f"/services?district={south.id}")
    assert "1 service found" in text
    assert "Demonstration Identity Card Replacement" in text


def test_filter_by_region_includes_all_its_districts(client, demo):
    region = db.session.query(Region).filter_by(name="Demonstration Region").one()
    assert "2 services found" in text_of(client, f"/services?region={region.id}")


def test_location_filter_ignores_archived_offices(client, demo):
    for office in db.session.query(GovernmentOffice):
        office.is_archived = True
    db.session.commit()
    region = db.session.query(Region).one()
    assert "0 services found" in text_of(client, f"/services?region={region.id}")


def test_filter_by_verification_status(client, demo):
    assert "3 services found" in text_of(client, "/services?status=pending")
    assert "0 services found" in text_of(client, "/services?status=verified")


def test_expired_service_is_found_under_outdated(client, sample):
    create_verification_records(sample.service)
    for record in sample.service.verification_records:
        record.status = "verified"
        record.source = sample.source
        record.last_checked_on = date.today() - timedelta(days=200)
        record.review_due_on = date.today() - timedelta(days=1)
        record.verified_by = sample.verifier
    db.session.commit()

    assert "1 service found" in text_of(client, "/services?status=outdated")
    assert "0 services found" in text_of(client, "/services?status=verified")


def test_filters_combine(client, demo):
    assert "0 services found" in text_of(
        client, "/services?category=business-registration&mode=physical"
    )


def test_chosen_filter_stays_selected(client, demo):
    text = text_of(client, "/services?mode=online")
    assert '<option value="online" selected>' in text
    assert "<details class=\"filter-panel\" open>" in text


# ---------- Invalid input ----------

@pytest.mark.parametrize("address", [
    "/services?category=not-real",
    "/services?institution=not-real",
    "/services?mode=teleport",
    "/services?status=approved",
    "/services?region=abc",
    "/services?district=999999",
    "/services?page=abc",
    "/services?page=-5",
])
def test_unknown_values_are_ignored(client, demo, address):
    assert "3 services found" in text_of(client, address)


def test_page_past_the_end_shows_the_last_page(client, demo):
    assert "Demonstration Business Name Filing" in text_of(client, "/services?page=999")


def test_special_characters_are_plain_text(client, demo):
    assert "0 services found" in text_of(client, "/services?q=%25")
    assert "0 services found" in text_of(client, "/services?q=_____")


def test_sql_injection_text_is_harmless(client, demo):
    text_of(client, "/services?q=' OR 1=1; DROP TABLE government_services; --")
    assert db.session.query(GovernmentService).count() == 3


def test_search_text_is_escaped(client, demo):
    text = text_of(client, "/services?q=<script>alert(1)</script>")
    assert "<script>alert(1)</script>" not in text
    assert "&lt;script&gt;" in text


def test_query_is_cleaned_and_shortened():
    assert clean_query("  many    spaces\x00here ") == "many spaces here"
    assert len(clean_query("x" * 500)) == 100


def test_search_words_handles_plurals_and_common_words():
    assert search_words("how to get passports") == ["passport"]
    assert search_words("the") == ["the"]


# ---------- Help when nothing is found ----------

def test_no_results_gives_guidance(client, demo):
    text = text_of(client, "/services?q=zzzzzz")
    assert "No services match your search." in text
    assert "may not be in our directory yet" in text


def test_spelling_suggestion_is_offered(client, demo):
    text = text_of(client, "/services?q=travl")
    assert "Did you mean" in text
    assert "/services?q=travel" in text


def test_spelling_suggestion_stays_quiet_without_a_match(demo):
    assert spelling_suggestion("zzzzzz") is None


def test_clear_filters_link_appears_when_filtering(client, demo):
    text = text_of(client, "/services?q=travel&mode=online")
    assert "clear all filters" in text


# ---------- Suggestions ----------

def test_suggestions_return_json(client, demo):
    response = client.get("/services/suggestions?q=travel")
    assert response.status_code == 200
    assert response.get_json() == {"suggestions": ["Demonstration Travel Document Renewal"]}


def test_suggestions_search_keywords(demo):
    assert suggest_services("trading") == ["Demonstration Business Name Filing"]


def test_very_short_text_gets_no_suggestions(demo):
    assert suggest_services("t") == []


def test_suggestions_hide_archived_services(sample):
    sample.service.is_archived = True
    db.session.commit()
    assert suggest_services("example") == []


def test_suggestions_are_not_logged(client, demo):
    client.get("/services/suggestions?q=travel")
    assert db.session.query(SearchLog).count() == 0


# ---------- Pagination ----------

def test_results_are_split_into_pages(client, sample):
    for number in range(RESULTS_PER_PAGE + 2):
        add_service(sample, f"Paged Service {number:02d}")

    first = text_of(client, "/services?q=paged")
    second = text_of(client, "/services?q=paged&page=2")

    assert f"{RESULTS_PER_PAGE + 2} services found" in first
    assert "Paged Service 00" in first and "Paged Service 11" not in first
    assert "Paged Service 11" in second and "Paged Service 00" not in second


def test_page_links_keep_the_search_and_filters(client, sample):
    for number in range(RESULTS_PER_PAGE + 1):
        add_service(sample, f"Paged Service {number:02d}", delivery_mode="online")

    text = text_of(client, "/services?q=paged&mode=online")
    assert "page=2" in text
    assert "q=paged" in text
    assert "mode=online" in text


# ---------- Search logging and privacy ----------

def test_search_is_logged_with_its_top_result(client, demo):
    client.get("/services?q=Travel")
    log = db.session.query(SearchLog).one()

    assert log.query_text == "travel"
    assert log.results_count == 1
    assert log.top_service_id is not None
    assert log.top_institution_id is not None


def test_failed_search_is_logged(client, demo):
    client.get("/services?q=zzzzzz")
    log = db.session.query(SearchLog).one()

    assert log.results_count == 0
    assert log.top_service_id is None


def test_browsing_without_text_is_not_logged(client, demo):
    client.get("/services")
    client.get("/services?mode=online")
    assert db.session.query(SearchLog).count() == 0


def test_later_pages_are_not_logged_again(client, demo):
    client.get("/services?q=travel&page=2")
    assert db.session.query(SearchLog).count() == 0


@pytest.mark.parametrize("typed, saved", [
    ("CM12345678ABCD passport", "passport"),
    ("my number 0772123456", "my number"),
    ("0772 123 456 replacement", "replacement"),
    ("person@example.test passport", "passport"),
    ("passport 2026", "passport 2026"),
    ("form 10", "form 10"),
])
def test_sensitive_text_is_removed(typed, saved):
    assert remove_sensitive_text(typed) == saved


def test_id_number_never_reaches_the_database(client, demo):
    client.get("/services?q=CM12345678ABCD")
    assert db.session.query(SearchLog).count() == 0


def test_log_failure_does_not_stop_search(client, demo, monkeypatch):
    def broken_commit():
        from sqlalchemy.exc import OperationalError
        raise OperationalError("INSERT", {}, Exception("database is locked"))

    monkeypatch.setattr(db.session, "commit", broken_commit)
    assert "1 service found" in text_of(client, "/services?q=travel")


# ---------- Rate limits ----------

def test_too_many_searches_are_slowed_down(monkeypatch):
    monkeypatch.setattr(TestingConfig, "RATELIMIT_ENABLED", True)
    limited_app = create_app("testing")

    with limited_app.app_context():
        db.create_all()
        client = limited_app.test_client()
        statuses = [client.get("/services").status_code for _ in range(61)]
        final = client.get("/services")
        db.session.remove()
        db.drop_all()

    assert statuses[:60] == [200] * 60
    assert final.status_code == 429
    assert "Please slow down" in final.get_data(as_text=True)


# ---------- Demonstration data ----------

def test_demo_seed_runs_once(database):
    assert seed_demo_data() == len(DEMO_SERVICES)
    assert seed_demo_data() == 0
    assert db.session.query(GovernmentService).count() == len(DEMO_SERVICES)


def test_every_demo_record_is_marked_and_named(demo):
    for service in db.session.query(GovernmentService):
        assert service.is_demo is True
        assert service.name.startswith("Demonstration")
    for institution in db.session.query(GovernmentInstitution):
        assert institution.is_demo is True
    for office in db.session.query(GovernmentOffice):
        assert office.is_demo is True


def test_demo_services_claim_no_facts(demo):
    for service in db.session.query(GovernmentService):
        assert service.fees == []
        assert service.documents == []
        assert service.processing == []
        assert len(service.verification_records) == 5
        assert {record.status for record in service.verification_records} == {"pending"}


def test_removing_demo_data_leaves_nothing_behind(database):
    seed_demo_data()
    assert remove_demo_data() == len(DEMO_SERVICES)

    for model in (GovernmentService, GovernmentInstitution, GovernmentOffice, District, Region):
        assert db.session.query(model).count() == 0
    assert db.session.query(ServiceCategory).count() == 14


def test_removing_demo_data_keeps_real_records(database):
    seed_demo_data()
    real = GovernmentInstitution(name="Real Institution", slug="real-institution")
    db.session.add(real)
    db.session.commit()

    remove_demo_data()
    assert db.session.query(GovernmentInstitution).one().name == "Real Institution"


def test_demo_commands_run(app, database):
    runner = app.test_cli_runner()
    assert "Added 3 demonstration services." in runner.invoke(args=["seed", "demo"]).output
    assert "Removed 3" in runner.invoke(args=["seed", "remove-demo"]).output
