"""Stage 11 Part A tests: managing records from the admin area.

All data here is invented for testing. Numbers such as 12345 are not real fees.
"""

import json
from datetime import date, timedelta

import pytest

from app.extensions import db
from app.logic.auth import create_admin
from app.logic.records import make_slug, unique_slug
from app.logic.verification import create_verification_records
from app.models import (
    AuditLog,
    District,
    GovernmentInstitution,
    GovernmentOffice,
    GovernmentService,
    OfficialSource,
    ProcessingInformation,
    Region,
    RequiredDocument,
    ServiceCategory,
    ServiceFee,
    ServiceOffice,
    ServiceVariant,
)

PASSWORD = "correct-horse-battery"
FUTURE = date.today() + timedelta(days=90)


def sign_in_as(client, role):
    email = f"{role.replace('_', '-')}@example.com"
    create_admin(f"Test {role}", email, PASSWORD, role)
    response = client.post("/admin/login", data={"email": email, "password": PASSWORD})
    assert response.status_code == 302


@pytest.fixture
def world(sample):
    """A real (non-demonstration) service with all five sections verified."""
    sample.service.is_demo = False
    sample.institution.is_demo = False
    sample.office.is_demo = False
    create_verification_records(sample.service)
    db.session.commit()
    verify_everything(sample)
    return sample


def verify_everything(data):
    for record in data.service.verification_records:
        record.status = "verified"
        record.source = data.source
        record.last_checked_on = date.today()
        record.review_due_on = FUTURE
        record.verified_by = data.verifier
    db.session.commit()


@pytest.fixture
def editor(client, world):
    sign_in_as(client, "editor")
    return client


def section(service, name):
    db.session.expire_all()
    return next(item for item in service.verification_records if item.section == name)


def statuses(service):
    db.session.expire_all()
    return {item.section: item.status for item in service.verification_records}


def post(client, address, **data):
    return client.post(address, data=data, follow_redirects=True)


def service_form(data, **changes):
    values = {
        "name": data.service.name, "summary": data.service.summary,
        "institution_id": data.institution.id, "category_id": data.category.id,
        "delivery_mode": "",
    }
    values.update(changes)
    return values


def row_address(data, kind, suffix="new"):
    return f"/admin/services/{data.service.id}/{kind}/{suffix}"


# ---------- Who can do what ----------

@pytest.mark.parametrize("address", [
    "/admin/services", "/admin/services/new", "/admin/institutions", "/admin/offices",
    "/admin/sources", "/admin/districts",
])
def test_every_admin_page_needs_login(client, database, address):
    response = client.get(address)
    assert response.status_code == 302
    assert "/admin/login" in response.headers["Location"]


def test_verifier_can_look_but_not_change(client, world):
    sign_in_as(client, "verifier")
    assert client.get("/admin/services").status_code == 200
    assert client.get(f"/admin/services/{world.service.id}").status_code == 200
    assert client.get("/admin/services/new").status_code == 403
    assert client.post(f"/admin/services/{world.service.id}/edit").status_code == 403
    assert client.post(row_address(world, "fees")).status_code == 403
    assert client.post("/admin/regions/new", data={"name": "Blocked"}).status_code == 403


def test_verifier_sees_no_edit_buttons(client, world):
    sign_in_as(client, "verifier")
    text = client.get(f"/admin/services/{world.service.id}").get_data(as_text=True)
    assert "Edit service details" not in text
    assert "Add fee" not in text


def test_super_admin_can_edit(client, world):
    sign_in_as(client, "super_admin")
    assert client.get("/admin/services/new").status_code == 200


# ---------- Services ----------

def test_new_service_starts_with_five_pending_sections(editor, world):
    response = post(editor, "/admin/services/new", **service_form(world, name="Brand New Service"))
    service = db.session.query(GovernmentService).filter_by(name="Brand New Service").one()

    assert "Every section starts as pending verification." in response.get_data(as_text=True)
    assert statuses(service) == dict.fromkeys(
        ["overview", "documents", "fees", "offices", "processing"], "pending"
    )
    assert service.slug == "brand-new-service"
    assert service.created_by.role == "editor"


def test_new_service_appears_to_citizens_as_pending(editor, client, world):
    post(editor, "/admin/services/new", **service_form(world, name="Brand New Service"))
    text = client.get("/services/brand-new-service").get_data(as_text=True)
    assert "Pending verification" in text


def test_required_fields_are_checked(editor, world):
    text = post(editor, "/admin/services/new", name="", summary="").get_data(as_text=True)
    assert "Enter the service name." in text
    assert "Enter the short summary." in text


def test_duplicate_service_name_is_explained(editor, world):
    text = post(editor, "/admin/services/new", **service_form(world)).get_data(as_text=True)
    assert "already in use" in text


@pytest.mark.parametrize("bad_link", ["javascript:alert(1)", "ftp://example.test", "example.test"])
def test_portal_must_be_a_web_link(editor, world, bad_link):
    text = post(
        editor, "/admin/services/new", **service_form(world, name="Bad", online_url=bad_link)
    ).get_data(as_text=True)
    assert "starting with http:// or https://" in text
    assert db.session.query(GovernmentService).count() == 1


def test_editing_details_resets_only_the_overview(editor, world):
    post(
        editor, f"/admin/services/{world.service.id}/edit",
        **service_form(world, summary="A changed summary"),
    )
    result = statuses(world.service)
    assert result["overview"] == "pending"
    assert result["fees"] == "verified"


def test_reset_clears_the_check_details_and_names_the_editor(editor, world):
    post(editor, f"/admin/services/{world.service.id}/edit", **service_form(world, summary="New"))
    record = section(world.service, "overview")

    assert record.verified_by is None
    assert record.last_checked_on is None
    assert record.review_due_on is None
    assert record.last_edited_by.role == "editor"


def test_saving_without_changes_keeps_verification(editor, world):
    post(editor, f"/admin/services/{world.service.id}/edit", **service_form(world))
    assert set(statuses(world.service).values()) == {"verified"}
    assert db.session.query(AuditLog).filter_by(action="update").count() == 0


def test_renaming_keeps_the_shared_link(editor, world):
    post(editor, f"/admin/services/{world.service.id}/edit", **service_form(world, name="Renamed"))
    db.session.expire_all()
    assert world.service.name == "Renamed"
    assert world.service.slug == "example-service"


def test_archiving_hides_a_service_and_restoring_brings_it_back(editor, client, world):
    address = f"/admin/services/{world.service.id}/archive"
    post(editor, address)
    assert client.get("/services/example-service").status_code == 404
    post(editor, address)
    assert client.get("/services/example-service").status_code == 200


def test_admin_search_finds_services(editor, world):
    assert "Example Service" in editor.get("/admin/services?q=example").get_data(as_text=True)
    assert "No services found." in editor.get("/admin/services?q=zzz").get_data(as_text=True)


def test_unknown_service_returns_404(editor, world):
    assert editor.get("/admin/services/99999").status_code == 404


# ---------- Fees ----------

def fee_values(**changes):
    values = {"fee_name": "Test fee", "fee_kind": "official", "service_speed": "ordinary",
              "is_mandatory": "y"}
    values.update(changes)
    return values


def test_blank_fee_stays_unconfirmed_and_zero_stays_free(editor, world):
    post(editor, row_address(world, "fees"), **fee_values(fee_name="Unknown", amount_ugx=""))
    post(editor, row_address(world, "fees"), **fee_values(fee_name="Free", amount_ugx="0"))

    fees = {fee.fee_name: fee.amount_ugx for fee in db.session.query(ServiceFee)}
    assert fees == {"Unknown": None, "Free": 0}


def test_adding_a_fee_resets_only_the_fees_section(editor, world):
    post(editor, row_address(world, "fees"), **fee_values(amount_ugx="12345"))
    result = statuses(world.service)
    assert result["fees"] == "pending"
    assert result["documents"] == "verified"


def test_changed_fee_stops_showing_on_the_citizen_page(editor, client, world):
    """The core promise: a changed amount can't appear until it's checked again."""
    fee = ServiceFee(service=world.service, fee_name="Test fee", amount_ugx=100)
    db.session.add(fee)
    db.session.commit()
    assert "UGX 100" in client.get("/services/example-service").get_data(as_text=True)

    post(editor, row_address(world, "fees", f"{fee.id}/edit"), **fee_values(amount_ugx="12345"))
    text = client.get("/services/example-service").get_data(as_text=True)

    assert "12,345" not in text
    assert "UGX 100" not in text
    assert "Official fee not yet verified" in text


def test_negative_fee_is_refused(editor, world):
    post(editor, row_address(world, "fees"), **fee_values(amount_ugx="-5"))
    assert db.session.query(ServiceFee).count() == 0


# ---------- Documents, processing and steps ----------

def test_document_answers_stay_not_confirmed_when_blank(editor, world):
    post(
        editor, row_address(world, "documents"), name="Paper", is_mandatory="y",
        original_required="", certified_copy_accepted="no", photocopies="",
    )
    document = db.session.query(RequiredDocument).one()

    assert document.original_required is None
    assert document.certified_copy_accepted is False
    assert document.photocopies is None


def test_unticked_box_makes_a_document_optional(editor, world):
    post(editor, row_address(world, "documents"), name="Paper")
    assert db.session.query(RequiredDocument).one().is_mandatory is False


def test_processing_days_must_be_in_order(editor, world):
    text = post(
        editor, row_address(world, "processing"), service_speed="ordinary",
        starts_after="unknown", basis="estimate", min_working_days="10", max_working_days="5",
    ).get_data(as_text=True)

    assert "can&#39;t be less than the minimum" in text or "can't be less than the minimum" in text
    assert db.session.query(ProcessingInformation).count() == 0


def test_step_changes_reset_the_overview(editor, world):
    post(editor, row_address(world, "steps"), step_number="1", stage="before_visit", title="Go")
    assert statuses(world.service)["overview"] == "pending"


def test_deleting_a_row_resets_its_section_and_is_audited(editor, world):
    document = RequiredDocument(service=world.service, name="Paper")
    db.session.add(document)
    db.session.commit()

    post(editor, row_address(world, "documents", f"{document.id}/delete"))
    entry = db.session.query(AuditLog).filter_by(action="delete").one()

    assert db.session.query(RequiredDocument).count() == 0
    assert statuses(world.service)["documents"] == "pending"
    assert json.loads(entry.old_values)["name"] == "Paper"


def test_rows_from_another_service_are_refused(editor, world):
    other = GovernmentService(
        institution=world.institution, category=world.category, name="Other",
        slug="other", summary="Example only",
    )
    document = RequiredDocument(service=other, name="Other paper")
    db.session.add_all([other, document])
    db.session.commit()

    assert editor.get(row_address(world, "documents", f"{document.id}/edit")).status_code == 404
    assert editor.post(row_address(world, "documents", f"{document.id}/delete")).status_code == 404
    assert db.session.query(RequiredDocument).count() == 1


def test_another_services_variant_cannot_be_chosen(editor, world):
    other = GovernmentService(
        institution=world.institution, category=world.category, name="Other",
        slug="other", summary="Example only",
    )
    variant = ServiceVariant(service=other, name="Other case")
    db.session.add_all([other, variant])
    db.session.commit()

    post(editor, row_address(world, "documents"), name="Paper", variant_id=variant.id)
    assert db.session.query(RequiredDocument).count() == 0


# ---------- Situations ----------

def test_only_one_situation_is_shown_first(editor, world):
    post(editor, row_address(world, "variants"), name="First", is_default="y")
    post(editor, row_address(world, "variants"), name="Second", is_default="y")
    db.session.expire_all()

    defaults = {variant.name: variant.is_default for variant in world.service.variants}
    assert defaults == {"First": False, "Second": True}


def test_deleting_a_situation_resets_every_section(editor, world):
    variant = ServiceVariant(service=world.service, name="Lost")
    db.session.add(variant)
    db.session.commit()

    post(editor, row_address(world, "variants", f"{variant.id}/delete"))
    assert set(statuses(world.service).values()) == {"pending"}


def test_duplicate_situation_is_explained(editor, world):
    post(editor, row_address(world, "variants"), name="Lost")
    text = post(editor, row_address(world, "variants"), name="Lost").get_data(as_text=True)
    assert "already in use" in text


# ---------- Linking offices ----------

def test_linking_an_office_starts_as_pending(editor, world):
    post(
        editor, f"/admin/services/{world.service.id}/offices/new",
        office_id=world.office.id, availability_note="Example note",
    )
    link = db.session.query(ServiceOffice).one()

    assert link.verification_status == "pending"
    assert statuses(world.service)["offices"] == "pending"


def test_linking_the_same_office_twice_is_explained(editor, world):
    address = f"/admin/services/{world.service.id}/offices/new"
    post(editor, address, office_id=world.office.id)
    text = post(editor, address, office_id=world.office.id).get_data(as_text=True)
    assert "already linked" in text


def test_removing_an_office_resets_the_section(editor, world):
    link = ServiceOffice(service=world.service, office=world.office)
    db.session.add(link)
    db.session.commit()
    verify_everything(world)

    post(editor, f"/admin/services/{world.service.id}/offices/{link.id}/delete")
    assert db.session.query(ServiceOffice).count() == 0
    assert statuses(world.service)["offices"] == "pending"


# ---------- Audit trail ----------

def test_audit_shows_old_and_new_values(editor, world):
    post(editor, f"/admin/services/{world.service.id}/edit", **service_form(world, summary="New"))
    entry = db.session.query(AuditLog).filter_by(action="update").one()

    assert json.loads(entry.old_values) == {"summary": "Example only"}
    assert json.loads(entry.new_values) == {"summary": "New"}
    assert entry.admin_user.role == "editor"
    assert entry.record_label == "Example Service"


def test_archiving_is_audited(editor, world):
    post(editor, f"/admin/services/{world.service.id}/archive")
    assert db.session.query(AuditLog).filter_by(action="archive").count() == 1


def test_refused_change_leaves_no_audit_entry(editor, world):
    post(editor, "/admin/services/new", **service_form(world))
    assert db.session.query(AuditLog).filter_by(action="create").count() == 0


# ---------- Institutions ----------

def institution_values(**changes):
    values = {"name": "New Ministry", "institution_type": "ministry"}
    values.update(changes)
    return values


def test_adding_an_institution_makes_a_slug(editor, world):
    post(editor, "/admin/institutions/new", **institution_values())
    institution = db.session.query(GovernmentInstitution).filter_by(name="New Ministry").one()
    assert institution.slug == "new-ministry"
    assert institution.verification_status == "pending"


def verify_institution(data):
    institution = data.institution
    institution.verification_status = "verified"
    institution.source_url = "https://example.test/agency"
    institution.last_verified_on = date.today()
    institution.review_due_on = FUTURE
    institution.verified_by = data.verifier
    db.session.commit()


def test_editing_a_verified_institution_makes_it_pending(editor, world):
    verify_institution(world)
    post(
        editor, f"/admin/institutions/{world.institution.id}/edit",
        **institution_values(name="Example Agency", institution_type="agency",
                             source_url="https://example.test/agency", phone="0000"),
    )
    db.session.expire_all()
    assert world.institution.verification_status == "pending"
    assert world.institution.verified_by is None


def test_institution_cannot_be_its_own_parent(editor, world):
    response = post(
        editor, f"/admin/institutions/{world.institution.id}/edit",
        **institution_values(name="Example Agency", parent_id=world.institution.id),
    )
    assert "Not a valid choice" in response.get_data(as_text=True)


def test_parent_loops_are_refused(editor, world):
    child = GovernmentInstitution(name="Child", slug="child", parent=world.institution)
    db.session.add(child)
    db.session.commit()

    text = post(
        editor, f"/admin/institutions/{world.institution.id}/edit",
        **institution_values(name="Example Agency", parent_id=child.id),
    ).get_data(as_text=True)
    assert "sit under itself" in text


def test_institution_with_open_services_cannot_be_archived(editor, world):
    text = post(editor, f"/admin/institutions/{world.institution.id}/archive").get_data(as_text=True)
    assert "services and offices first" in text
    db.session.expire_all()
    assert world.institution.is_archived is False


def test_empty_institution_can_be_archived_and_restored(editor, world):
    empty = GovernmentInstitution(name="Empty", slug="empty")
    db.session.add(empty)
    db.session.commit()

    post(editor, f"/admin/institutions/{empty.id}/archive")
    db.session.expire_all()
    assert empty.is_archived is True
    post(editor, f"/admin/institutions/{empty.id}/archive")
    db.session.expire_all()
    assert empty.is_archived is False


def test_invalid_email_is_refused(editor, world):
    text = post(
        editor, "/admin/institutions/new", **institution_values(email="not-an-email")
    ).get_data(as_text=True)
    assert "Enter a valid email address." in text


# ---------- Offices ----------

def office_values(data, **changes):
    values = {
        "name": data.office.name, "institution_id": data.institution.id,
        "district_id": data.district.id, "office_type": "district",
    }
    values.update(changes)
    return values


def test_adding_an_office(editor, world):
    post(editor, "/admin/offices/new", **office_values(world, name="Added Office"))
    office = db.session.query(GovernmentOffice).filter_by(name="Added Office").one()
    assert office.physical_address is None
    assert office.latitude is None


def test_coordinates_must_come_together(editor, world):
    text = post(
        editor, "/admin/offices/new", **office_values(world, name="Half", latitude="2.5")
    ).get_data(as_text=True)
    assert "both latitude and longitude" in text


def test_coordinates_are_saved_as_numbers(editor, world):
    post(
        editor, "/admin/offices/new",
        **office_values(world, name="Mapped", latitude="2.5", longitude="32.5"),
    )
    office = db.session.query(GovernmentOffice).filter_by(name="Mapped").one()
    assert float(office.latitude) == 2.5
    assert float(office.longitude) == 32.5


def test_editing_an_office_resets_its_services_offices_section(editor, world):
    link = ServiceOffice(
        service=world.service, office=world.office, verification_status="verified",
        source=world.source, last_verified_on=date.today(),
    )
    db.session.add(link)
    db.session.commit()

    post(
        editor, f"/admin/offices/{world.office.id}/edit",
        **office_values(world, physical_address="A changed address"),
    )
    db.session.expire_all()

    assert link.verification_status == "pending"
    assert statuses(world.service)["offices"] == "pending"
    assert statuses(world.service)["fees"] == "verified"


# ---------- Sources ----------

def source_values(data, **changes):
    values = {
        "title": data.source.title, "url": data.source.url,
        "institution_id": data.institution.id, "source_type": "web_page",
    }
    values.update(changes)
    return values


def test_source_needs_a_real_web_link(editor, world):
    text = post(
        editor, "/admin/sources/new",
        **source_values(world, title="Bad", url="javascript:alert(1)"),
    ).get_data(as_text=True)
    assert "starting with http:// or https://" in text


def test_duplicate_source_is_explained(editor, world):
    text = post(editor, "/admin/sources/new", **source_values(world)).get_data(as_text=True)
    assert "already in use" in text


def test_changing_a_source_address_resets_what_relies_on_it(editor, world):
    post(
        editor, f"/admin/sources/{world.source.id}/edit",
        **source_values(world, url="https://example.test/moved"),
    )
    assert set(statuses(world.service).values()) == {"pending"}


def test_changing_a_source_title_keeps_verification(editor, world):
    post(
        editor, f"/admin/sources/{world.source.id}/edit",
        **source_values(world, title="A clearer title"),
    )
    assert set(statuses(world.service).values()) == {"verified"}


def test_source_in_use_cannot_be_deleted(editor, world):
    text = post(editor, f"/admin/sources/{world.source.id}/delete").get_data(as_text=True)
    assert "still in use" in text
    assert db.session.query(OfficialSource).count() == 1


def test_unused_source_can_be_deleted(editor, world):
    unused = OfficialSource(institution=world.institution, title="Unused",
                            url="https://example.test/unused")
    db.session.add(unused)
    db.session.commit()
    post(editor, f"/admin/sources/{unused.id}/delete")
    assert db.session.query(OfficialSource).count() == 1


# ---------- Categories, regions and districts ----------

def test_adding_a_category(editor, client, world):
    post(editor, "/admin/categories/new", name="New Category", is_active="y", display_order="0")
    assert "New Category" in client.get("/services").get_data(as_text=True)


def test_hiding_a_category(editor, client, world):
    post(editor, f"/admin/categories/{world.category.id}/edit", name="Example Category")
    assert "Example Category" not in client.get("/").get_data(as_text=True)


def test_category_in_use_cannot_be_deleted(editor, world):
    text = post(editor, f"/admin/categories/{world.category.id}/delete").get_data(as_text=True)
    assert "still in use" in text
    assert db.session.query(ServiceCategory).count() == 1


def test_region_and_district_can_be_added(editor, world):
    post(editor, "/admin/regions/new", name="Added Region")
    region = db.session.query(Region).filter_by(name="Added Region").one()
    post(editor, "/admin/districts/new", name="Added District", region_id=region.id,
         sub_region="Added Sub-region")

    district = db.session.query(District).filter_by(name="Added District").one()
    assert district.region is region
    assert district.sub_region == "Added Sub-region"


def test_region_with_districts_cannot_be_deleted(editor, world):
    text = post(editor, f"/admin/regions/{world.region.id}/delete").get_data(as_text=True)
    assert "still in use" in text


def test_offices_cannot_be_deleted_only_archived(editor, world):
    assert editor.post(f"/admin/offices/{world.office.id}/delete").status_code == 404


def test_sources_have_no_archive(editor, world):
    assert editor.post(f"/admin/sources/{world.source.id}/archive").status_code == 404


def test_unknown_record_returns_404(editor, world):
    assert editor.get("/admin/offices/99999/edit").status_code == 404


def test_unknown_kind_returns_404(editor, world):
    assert editor.get("/admin/secrets").status_code == 404


# ---------- Safety and pages ----------

@pytest.mark.parametrize("kind", [
    "institutions", "offices", "sources", "categories", "regions", "districts",
])
def test_list_and_form_pages_load(editor, world, kind):
    assert editor.get(f"/admin/{kind}").status_code == 200
    assert editor.get(f"/admin/{kind}/new").status_code == 200


def test_edit_forms_show_existing_values(editor, world):
    world.service.summary = "A stored summary"
    db.session.commit()
    text = editor.get(f"/admin/services/{world.service.id}/edit").get_data(as_text=True)
    assert "A stored summary" in text


def test_stored_text_is_escaped_in_admin_pages(editor, world):
    world.service.name = "<script>bad()</script>"
    db.session.commit()
    text = editor.get(f"/admin/services/{world.service.id}").get_data(as_text=True)
    assert "<script>bad()</script>" not in text


def test_slugs_are_safe_and_unique(world):
    assert make_slug("Land & Property: Title!") == "land-property-title"
    assert unique_slug(GovernmentService, "Example Service") == "example-service-2"


def test_actions_cannot_be_triggered_by_a_link(editor, world):
    assert editor.get(f"/admin/services/{world.service.id}/archive").status_code == 405
    assert editor.get(f"/admin/sources/{world.source.id}/delete").status_code == 405
