"""Stage 9 tests: the institution directory and the office finder.

All data here is invented for testing.
"""

from datetime import date, timedelta

import pytest

from app.extensions import db
from app.logic.search import RESULTS_PER_PAGE
from app.models import (
    DailyView,
    District,
    GovernmentInstitution,
    GovernmentOffice,
    Region,
    ServiceOffice,
)


def text_of(client, address):
    response = client.get(address)
    assert response.status_code == 200
    return response.get_data(as_text=True)


@pytest.fixture
def world(sample):
    """Two regions, with offices spread across them. All invented."""
    sample.other_region = Region(name="Other Region")
    sample.same_region_district = District(name="Neighbour District", region=sample.region)
    sample.empty_district = District(name="Empty District", region=sample.region)
    sample.far_district = District(name="Far District", region=sample.other_region)

    sample.other_institution = GovernmentInstitution(
        name="Other Ministry", slug="other-ministry", acronym="OM",
        institution_type="ministry", description="Looks after example matters.",
    )
    sample.neighbour_office = GovernmentOffice(
        institution=sample.institution, district=sample.same_region_district,
        name="Neighbour Office",
    )
    sample.far_office = GovernmentOffice(
        institution=sample.other_institution, district=sample.far_district, name="Far Office",
    )
    sample.headquarters = GovernmentOffice(
        institution=sample.institution, district=sample.district,
        name="Aaa Headquarters", office_type="headquarters",
    )
    db.session.add_all([
        sample.other_region, sample.empty_district, sample.other_institution,
        sample.neighbour_office, sample.far_office, sample.headquarters,
        ServiceOffice(service=sample.service, office=sample.office,
                      availability_note="Example note about this office"),
    ])
    db.session.commit()
    return sample


# ---------- Institution directory ----------

def test_directory_lists_institutions(client, world):
    text = text_of(client, "/institutions")
    assert "2 institutions found" in text
    assert "Example Agency" in text
    assert "Other Ministry" in text


@pytest.mark.parametrize("address, expected", [
    ("/institutions?q=other", "Other Ministry"),
    ("/institutions?q=OM", "Other Ministry"),
    ("/institutions?q=example+matters", "Other Ministry"),
    ("/institutions?type=ministry", "Other Ministry"),
])
def test_institutions_can_be_searched(client, world, address, expected):
    text = text_of(client, address)
    assert "1 institution found" in text
    assert expected in text


def test_institution_counts_ignore_archived_records(client, world):
    world.service.is_archived = True
    world.far_office.is_archived = True
    db.session.commit()
    text = text_of(client, "/institutions?q=other")
    assert "0 services · 0 offices" in text


def test_archived_institution_is_hidden(client, world):
    world.other_institution.is_archived = True
    db.session.commit()
    assert "Other Ministry" not in text_of(client, "/institutions")
    assert client.get("/institutions/other-ministry").status_code == 404


def test_no_matching_institution_gives_guidance(client, world):
    text = text_of(client, "/institutions?q=zzzzzz")
    assert "No institutions match your search." in text
    assert "may not be in our directory yet" in text


@pytest.mark.parametrize("address", ["/institutions?type=alien", "/institutions?page=abc"])
def test_unknown_institution_values_are_ignored(client, world, address):
    assert "2 institutions found" in text_of(client, address)


def test_institution_search_text_is_escaped(client, world):
    text = text_of(client, "/institutions?q=<script>bad()</script>")
    assert "<script>bad()</script>" not in text


def test_institutions_are_paged(client, world):
    for number in range(RESULTS_PER_PAGE):
        db.session.add(GovernmentInstitution(name=f"Paged {number}", slug=f"paged-{number}"))
    db.session.commit()
    text = text_of(client, "/institutions")
    assert f"{RESULTS_PER_PAGE + 2} institutions found" in text
    assert "/institutions?page=2" in text


# ---------- Institution page ----------

def test_institution_page_shows_services_and_offices(client, world):
    text = text_of(client, "/institutions/example-agency")
    assert "Example Service" in text
    assert 'href="/services/example-service"' in text
    assert "Example Office" in text


def test_unknown_institution_returns_404(client, world):
    assert client.get("/institutions/no-such-body").status_code == 404


def test_missing_contact_details_are_not_invented(client, world):
    text = text_of(client, "/institutions/other-ministry")
    assert text.count("Not confirmed") >= 4
    assert "tel:" not in text
    assert "mailto:" not in text


def test_unverified_institution_carries_a_warning(client, world):
    text = text_of(client, "/institutions/other-ministry")
    assert "Pending verification" in text
    assert "haven't been confirmed as current" in text


def verify_institution(world, review_due_on):
    institution = world.other_institution
    institution.verification_status = "verified"
    institution.source_url = "https://example.test/ministry"
    institution.last_verified_on = date.today() - timedelta(days=10)
    institution.review_due_on = review_due_on
    institution.verified_by = world.verifier
    db.session.commit()


def test_verified_institution_shows_dates_and_source(client, world):
    verify_institution(world, date.today() + timedelta(days=30))
    text = text_of(client, "/institutions/other-ministry")

    assert "haven't been confirmed as current" not in text
    assert "Last checked:" in text
    assert 'href="https://example.test/ministry"' in text


def test_expired_institution_shows_as_outdated(client, world):
    verify_institution(world, date.today() - timedelta(days=1))
    assert "status-badge status-outdated" in text_of(client, "/institutions/other-ministry")


def test_parent_and_child_institutions_are_linked(client, world):
    world.institution.parent = world.other_institution
    db.session.commit()

    assert 'href="/institutions/other-ministry"' in text_of(client, "/institutions/example-agency")
    assert 'href="/institutions/example-agency"' in text_of(client, "/institutions/other-ministry")


def test_archived_parent_is_not_linked(client, world):
    world.institution.parent = world.other_institution
    world.other_institution.is_archived = True
    db.session.commit()
    assert "Other Ministry" not in text_of(client, "/institutions/example-agency")


def test_demo_institution_says_it_is_fictional(client, world):
    assert "It doesn't exist." in text_of(client, "/institutions/example-agency")


def test_institution_page_lists_local_offices_before_headquarters(client, world):
    text = text_of(client, "/institutions/example-agency")
    assert text.index("Example Office") < text.index("Aaa Headquarters")


def test_opening_an_institution_counts_a_view(client, world):
    text_of(client, "/institutions/example-agency")
    text_of(client, "/institutions/example-agency")
    view = db.session.query(DailyView).one()

    assert view.institution_id == world.institution.id
    assert view.service_id is None
    assert view.view_count == 2


def test_checklist_links_to_its_institution(client, world):
    text = text_of(client, "/services/example-service")
    assert 'href="/institutions/example-agency"' in text


# ---------- Find an office ----------

def test_all_open_offices_are_listed(client, world):
    assert "4 offices found" in text_of(client, "/offices")


def test_local_offices_come_before_headquarters(client, world):
    text = text_of(client, "/offices")
    assert text.index("Example Office") < text.index("Aaa Headquarters")


def test_filter_by_district(client, world):
    text = text_of(client, f"/offices?district={world.same_region_district.id}")
    assert "1 office found" in text
    assert "Neighbour Office" in text


def test_filter_by_region(client, world):
    assert "3 offices found" in text_of(client, f"/offices?region={world.region.id}")


def test_filter_by_institution(client, world):
    text = text_of(client, "/offices?institution=other-ministry")
    assert "1 office found" in text
    assert "Far Office" in text


def test_filter_by_service(client, world):
    text = text_of(client, "/offices?service=example-service")
    assert "1 office found" in text
    assert "Example Office" in text


def test_filters_combine(client, world):
    address = f"/offices?service=example-service&region={world.other_region.id}"
    assert "0 offices found" in text_of(client, address)


def test_empty_district_falls_back_to_its_region_and_says_so(client, world):
    text = text_of(client, f"/offices?district={world.empty_district.id}")
    assert "We haven't listed a matching office in Empty District." in text
    assert "elsewhere in the same region" in text
    assert "3 offices found" in text
    assert "Far Office" not in text


def test_fallback_does_not_claim_offices_when_there_are_none(client, world):
    address = f"/offices?district={world.empty_district.id}&institution=other-ministry"
    text = text_of(client, address)
    assert "We haven't listed a matching office in Empty District." in text
    assert "elsewhere in the same region" not in text
    assert "No offices match your choices." in text


def test_archived_office_is_hidden(client, world):
    world.far_office.is_archived = True
    db.session.commit()
    assert "Far Office" not in text_of(client, "/offices")


def test_office_shows_its_services_and_notes(client, world):
    text = text_of(client, "/offices")
    assert 'href="/services/example-service"' in text
    assert "Example note about this office" in text


def test_archived_service_is_not_listed_at_an_office(client, world):
    world.service.is_archived = True
    db.session.commit()
    assert "Example Service" not in text_of(client, "/offices")


def test_office_without_services_says_so(client, world):
    assert "No services have been listed for this office yet." in text_of(client, "/offices")


def test_unconfirmed_address_is_not_invented(client, world):
    assert "Address not yet verified" in text_of(client, "/offices")


def test_location_is_ready_for_maps_only_when_known(client, world):
    assert "data-latitude" not in text_of(client, "/offices")

    world.far_office.latitude = 2.5
    world.far_office.longitude = 32.5
    db.session.commit()
    text = text_of(client, "/offices")
    assert 'data-latitude="2.5"' in text
    assert 'data-longitude="32.5"' in text


def test_demo_office_is_labelled(client, world):
    assert "Demonstration only" in text_of(client, "/offices")


@pytest.mark.parametrize("query", [
    "district=abc", "district=999999", "region=abc", "institution=not-real",
    "service=not-real", "page=abc", "page=-3",
])
def test_unknown_office_values_are_ignored(client, world, query):
    assert "4 offices found" in text_of(client, f"/offices?{query}")


def test_chosen_filter_stays_selected(client, world):
    text = text_of(client, "/offices?institution=other-ministry")
    assert '<option value="other-ministry" selected>' in text


def test_offices_are_paged_and_keep_filters(client, world):
    for number in range(RESULTS_PER_PAGE):
        db.session.add(GovernmentOffice(
            institution=world.other_institution, district=world.far_district,
            name=f"Paged Office {number}",
        ))
    db.session.commit()
    text = text_of(client, "/offices?institution=other-ministry")
    assert "page=2" in text
    assert "institution=other-ministry" in text


def test_empty_directory_is_honest(client, database):
    assert "No offices match your choices." in text_of(client, "/offices")
    assert "No institutions match your search." in text_of(client, "/institutions")
