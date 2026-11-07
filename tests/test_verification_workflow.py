"""Stage 11 Part B tests: reviewing information against official sources.

All data here is invented. Numbers such as 12345 are not real fees.
"""

import json
from datetime import date, timedelta

import pytest

from app import create_app
from app.extensions import db
from app.logic.auth import create_admin
from app.logic.checklist import FEE_NOT_VERIFIED_MESSAGE
from app.logic.review import (
    DUE_SOON_DAYS,
    ReviewRefused,
    build_queue,
    describe_changes,
    last_editor_id,
    review_section,
    section_problems,
)
from app.logic.verification import create_verification_records
from app.models import (
    AuditLog,
    GovernmentInstitution,
    GovernmentService,
    ProcessingInformation,
    RequiredDocument,
    ServiceCategory,
    ServiceFee,
    ServiceOffice,
)

PASSWORD = "correct-horse-battery"
TODAY = date.today()
FUTURE = TODAY + timedelta(days=180)


def sign_in_as(client, role):
    email = f"{role.replace('_', '-')}@example.com"
    admin = create_admin(f"Test {role}", email, PASSWORD, role)
    assert client.post(
        "/admin/login", data={"email": email, "password": PASSWORD}
    ).status_code == 302
    return admin


@pytest.fixture
def world(sample):
    """A real service with content in every section, edited by the sample editor."""
    service = sample.service
    service.is_demo = False
    service.eligibility = "Example people"
    service.delivery_mode = "physical"
    sample.institution.is_demo = False
    sample.office.is_demo = False
    create_verification_records(service, sample.editor)
    db.session.add_all([
        RequiredDocument(service=service, name="Paper"),
        ServiceFee(service=service, fee_name="Test fee", amount_ugx=12345),
        ProcessingInformation(service=service, min_working_days=1, max_working_days=2),
    ])
    sample.link = ServiceOffice(service=service, office=sample.office)
    db.session.add(sample.link)
    db.session.commit()
    return sample


@pytest.fixture
def reviewer(client, world):
    world.reviewer = sign_in_as(client, "verifier")
    return client


def record_for(data, section):
    db.session.expire_all()
    return next(r for r in data.service.verification_records if r.section == section)


def decision(data, **changes):
    values = {
        "status": "verified",
        "source_id": data.source.id,
        "last_checked_on": TODAY.isoformat(),
        "review_due_on": FUTURE.isoformat(),
    }
    values.update(changes)
    return values


def submit(client, data, section="fees", **changes):
    return client.post(
        f"/admin/services/{data.service.id}/review/{section}",
        data=decision(data, **changes),
        follow_redirects=True,
    )


# ---------- Who can review ----------

def test_review_needs_login(client, world):
    address = f"/admin/services/{world.service.id}/review/fees"
    assert client.get(address).status_code == 302


def test_editor_cannot_review(client, world):
    sign_in_as(client, "editor")
    address = f"/admin/services/{world.service.id}/review/fees"
    assert client.get(address).status_code == 403
    assert client.post(address, data=decision(world)).status_code == 403
    assert record_for(world, "fees").status == "pending"


def test_queue_is_visible_to_every_admin(client, world):
    sign_in_as(client, "editor")
    text = client.get("/admin/verification").get_data(as_text=True)
    assert "Waiting for review" in text
    assert ">Review</a>" not in text


# ---------- Verifying ----------

def test_verifier_can_verify_a_section(reviewer, world):
    text = submit(reviewer, world).get_data(as_text=True)
    record = record_for(world, "fees")

    assert "Your decision was saved." in text
    assert record.status == "verified"
    assert record.verified_by.id == world.reviewer.id
    assert record.last_checked_on == TODAY
    assert record.review_due_on == FUTURE


def test_verified_fee_appears_for_citizens(reviewer, client, world):
    assert "12,345" not in client.get("/services/example-service").get_data(as_text=True)
    submit(reviewer, world)
    assert "UGX 12,345" in client.get("/services/example-service").get_data(as_text=True)


def test_verifying_updates_the_source_check_date(reviewer, world):
    submit(reviewer, world)
    db.session.expire_all()
    assert world.source.last_checked_on == TODAY


def test_review_page_shows_hidden_details_for_comparison(reviewer, world):
    record_for(world, "fees").source = world.source
    db.session.commit()
    address = f"/admin/services/{world.service.id}/review/fees"
    text = reviewer.get(address).get_data(as_text=True)
    assert "UGX 12,345" in text
    assert world.source.url in text


def test_review_is_audited_with_old_and_new_values(reviewer, world):
    submit(reviewer, world)
    entry = db.session.query(AuditLog).filter_by(action="verify").one()

    assert entry.admin_user_id == world.reviewer.id
    assert entry.record_label == "Example Service: fees"
    assert json.loads(entry.old_values)["status"] == "pending"
    assert json.loads(entry.new_values)["status"] == "verified"


# ---------- Refusals ----------

def test_nobody_can_verify_their_own_edit(client, world):
    admin = sign_in_as(client, "super_admin")
    record = record_for(world, "fees")
    record.last_edited_by_id = admin.id
    db.session.commit()

    text = submit(client, world).get_data(as_text=True)
    assert "a different person must verify it" in text
    assert record_for(world, "fees").status == "pending"


def test_service_creator_cannot_verify_it(world):
    service = GovernmentService(
        institution=world.institution, category=world.category, name="New",
        slug="new", summary="Example only", eligibility="Anyone", delivery_mode="online",
    )
    create_verification_records(service, world.verifier)
    db.session.add(service)
    db.session.commit()
    record = next(r for r in service.verification_records if r.section == "overview")

    with pytest.raises(ReviewRefused, match="different person"):
        review_section(record, world.verifier, "verified", world.source.id, TODAY, FUTURE, None)


def test_demo_service_cannot_be_verified(reviewer, world):
    world.service.is_demo = True
    db.session.commit()
    text = submit(reviewer, world).get_data(as_text=True)
    assert "can never be verified" in text
    assert record_for(world, "fees").status == "pending"


@pytest.mark.parametrize("changes, message", [
    ({"source_id": ""}, "Choose the official source you checked."),
    ({"review_due_on": ""}, "Enter a review date to verify this."),
    ({"review_due_on": TODAY.isoformat()}, "must be after the check date"),
    ({"last_checked_on": (TODAY + timedelta(days=1)).isoformat()}, "be in the future"),
    ({"last_checked_on": ""}, "Enter the date you checked."),
])
def test_bad_evidence_is_refused(reviewer, world, changes, message):
    text = submit(reviewer, world, **changes).get_data(as_text=True).replace("&#39;", "'")
    assert message in text
    assert record_for(world, "fees").status == "pending"


def test_unknown_status_is_refused(reviewer, world):
    submit(reviewer, world, status="approved-by-magic")
    assert record_for(world, "fees").status == "pending"


@pytest.mark.parametrize("section, attribute, message", [
    ("documents", "documents", "No documents have been added."),
    ("fees", "fees", "No fees have been added."),
    ("processing", "processing", "No processing time has been added."),
])
def test_empty_section_cannot_be_verified(reviewer, world, section, attribute, message):
    getattr(world.service, attribute).clear()
    db.session.commit()
    assert message in submit(reviewer, world, section).get_data(as_text=True)
    assert record_for(world, section).status == "pending"


def test_overview_needs_its_key_facts(world):
    world.service.eligibility = None
    world.service.delivery_mode = None
    assert len(section_problems(world.service, "overview")) == 2


def test_offices_section_needs_verified_links(reviewer, world):
    text = submit(reviewer, world, "offices").get_data(as_text=True)
    assert "Every linked office must be verified first." in text


def test_offices_section_needs_a_link(world):
    db.session.delete(world.link)
    db.session.commit()
    db.session.expire_all()
    assert "No offices have been linked." in section_problems(world.service, "offices")


def test_page_warns_before_a_doomed_review(client, world):
    admin = sign_in_as(client, "super_admin")
    record = record_for(world, "fees")
    record.last_edited_by_id = admin.id
    db.session.commit()
    text = client.get(f"/admin/services/{world.service.id}/review/fees").get_data(as_text=True)
    assert "a different person must verify it" in text


# ---------- Other decisions ----------

def test_section_can_be_marked_unavailable_without_evidence(reviewer, world):
    submit(reviewer, world, status="unavailable", source_id="", review_due_on="")
    record = record_for(world, "fees")

    assert record.status == "unavailable"
    assert record.verified_by is None
    assert db.session.query(AuditLog).filter_by(action="status_change").count() == 1


def test_verified_section_can_be_marked_outdated(reviewer, world):
    submit(reviewer, world)
    submit(reviewer, world, status="outdated", review_due_on="")
    record = record_for(world, "fees")

    assert record.status == "outdated"
    assert record.verified_by is None
    assert record.review_due_on is None


# ---------- Office links, offices and institutions ----------

def link_address(data):
    return f"/admin/services/{data.service.id}/offices/{data.link.id}/review"


def link_decision(data, **changes):
    values = {"status": "verified", "source_id": data.source.id,
              "last_checked_on": TODAY.isoformat()}
    values.update(changes)
    return values


def test_office_link_can_be_verified_then_its_section(reviewer, world):
    reviewer.post(link_address(world), data=link_decision(world))
    db.session.expire_all()
    assert world.link.verification_status == "verified"

    submit(reviewer, world, "offices")
    assert record_for(world, "offices").status == "verified"


def test_downgrading_a_link_resets_its_section(reviewer, world):
    reviewer.post(link_address(world), data=link_decision(world))
    submit(reviewer, world, "offices")
    reviewer.post(link_address(world), data=link_decision(world, status="pending", source_id=""))
    assert record_for(world, "offices").status == "pending"


def test_link_review_needs_a_source(reviewer, world):
    reviewer.post(link_address(world), data=link_decision(world, source_id=""))
    db.session.expire_all()
    assert world.link.verification_status == "pending"


def test_link_from_another_service_returns_404(reviewer, world):
    address = f"/admin/services/99999/offices/{world.link.id}/review"
    assert reviewer.get(address).status_code == 404


def test_office_can_be_verified(reviewer, client, world):
    reviewer.post(f"/admin/offices/{world.office.id}/review", data=decision(world))
    db.session.expire_all()

    assert world.office.verification_status == "verified"
    assert world.office.verified_by.id == world.reviewer.id


def test_institution_can_be_verified_with_its_page(reviewer, world):
    reviewer.post(
        f"/admin/institutions/{world.institution.id}/review",
        data=decision(world, source_url="https://example.test/agency"),
    )
    db.session.expire_all()
    assert world.institution.verification_status == "verified"


def test_institution_needs_an_official_page(reviewer, world):
    reviewer.post(f"/admin/institutions/{world.institution.id}/review", data=decision(world))
    db.session.expire_all()
    assert world.institution.verification_status == "pending"


def test_institution_page_must_be_a_web_link(reviewer, world):
    reviewer.post(
        f"/admin/institutions/{world.institution.id}/review",
        data=decision(world, source_url="javascript:alert(1)"),
    )
    db.session.expire_all()
    assert world.institution.verification_status == "pending"


def test_last_editor_comes_from_the_audit_trail(client, world):
    admin = sign_in_as(client, "super_admin")
    client.post(f"/admin/institutions/{world.institution.id}/edit", data={
        "name": "Renamed Agency", "institution_type": "agency",
    })
    assert last_editor_id("government_institutions", world.institution.id) == admin.id

    text = client.post(
        f"/admin/institutions/{world.institution.id}/review",
        data=decision(world, source_url="https://example.test/agency"),
        follow_redirects=True,
    ).get_data(as_text=True)
    assert "a different person must verify it" in text


def test_demo_office_cannot_be_verified(reviewer, world):
    world.office.is_demo = True
    db.session.commit()
    text = reviewer.post(
        f"/admin/offices/{world.office.id}/review", data=decision(world), follow_redirects=True
    ).get_data(as_text=True)
    assert "can never be verified" in text


# ---------- The review queue ----------

def names_in(items):
    return [item["name"] for item in items]


def test_new_records_wait_for_review(world):
    queue = build_queue(TODAY)
    assert len([item for item in queue["waiting"] if item["name"] == "Example Service"]) == 5
    assert "Example Agency" in names_in(queue["waiting"])
    assert "Example Office" in names_in(queue["waiting"])


def verify_directly(data, section, due):
    record = next(r for r in data.service.verification_records if r.section == section)
    record.status = "verified"
    record.source = data.source
    record.last_checked_on = TODAY - timedelta(days=200)
    record.review_due_on = due
    record.verified_by = data.verifier
    record.last_edited_by = None
    db.session.commit()


def test_expired_section_is_overdue(world):
    verify_directly(world, "fees", TODAY - timedelta(days=1))
    queue = build_queue(TODAY)
    assert [item["kind"] for item in queue["overdue"]] == ["Fees"]


def test_section_due_soon_is_flagged(world):
    verify_directly(world, "fees", TODAY + timedelta(days=DUE_SOON_DAYS))
    assert [item["kind"] for item in build_queue(TODAY)["due_soon"]] == ["Fees"]


def test_section_due_later_needs_no_action(world):
    verify_directly(world, "fees", TODAY + timedelta(days=DUE_SOON_DAYS + 1))
    queue = build_queue(TODAY)
    assert queue["due_soon"] == []
    assert "Fees" not in [item["kind"] for item in queue["waiting"]]


def test_demo_and_archived_records_are_left_out(world):
    world.service.is_demo = True
    world.institution.is_demo = True
    world.office.is_archived = True
    db.session.commit()
    assert build_queue(TODAY) == {"overdue": [], "waiting": [], "due_soon": []}


def test_every_queue_link_opens(reviewer, world):
    text = reviewer.get("/admin/verification").get_data(as_text=True)
    assert text.count(">Review</a>") == 8
    assert reviewer.get(f"/admin/services/{world.service.id}/review/overview").status_code == 200
    assert reviewer.get(link_address(world)).status_code == 200
    assert reviewer.get(f"/admin/offices/{world.office.id}/review").status_code == 200
    assert reviewer.get(f"/admin/institutions/{world.institution.id}/review").status_code == 200


def test_manage_page_offers_review_to_verifiers(reviewer, world):
    text = reviewer.get(f"/admin/services/{world.service.id}").get_data(as_text=True)
    assert f"/admin/services/{world.service.id}/review/fees" in text


# ---------- History ----------

def test_history_needs_login(client, database):
    assert client.get("/admin/history").status_code == 302


def test_history_shows_who_changed_what(reviewer, world):
    submit(reviewer, world)
    text = reviewer.get("/admin/history").get_data(as_text=True)
    assert "Example Service: fees" in text
    assert "Test verifier" in text
    assert "pending → verified" in text


def test_history_can_be_filtered(reviewer, world):
    submit(reviewer, world)
    text = reviewer.get("/admin/history?action=verify").get_data(as_text=True)
    assert "Verify: Example Service: fees" in text
    assert "Login:" not in text


def test_unknown_history_filter_is_ignored(reviewer, world):
    assert reviewer.get("/admin/history?action=hack&page=abc").status_code == 200


def test_history_never_shows_password_details(reviewer, world):
    assert "scrypt" not in reviewer.get("/admin/history").get_data(as_text=True)


def test_history_text_is_escaped(reviewer, world):
    db.session.add(AuditLog(action="update", table_name="x", record_label="<script>bad()</script>"))
    db.session.commit()
    assert "<script>bad()</script>" not in reviewer.get("/admin/history").get_data(as_text=True)


def test_changes_are_readable():
    changes = describe_changes('{"status": "pending", "notes": null}', '{"status": "verified", "notes": "Ok"}')
    assert {"field": "Status", "old": "pending", "new": "verified"} in changes
    assert {"field": "Notes", "old": "empty", "new": "Ok"} in changes


# ---------- The whole journey, with two real people ----------

def test_two_people_take_a_fee_from_entry_to_citizens():
    """Each client signs in separately, as two people would on a real server."""
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        create_admin("Editor", "editor@example.com", PASSWORD, "editor")
        create_admin("Verifier", "verifier@example.com", PASSWORD, "verifier")
        institution = GovernmentInstitution(name="Agency", slug="agency")
        category = ServiceCategory(name="Category", slug="category")
        db.session.add_all([institution, category])
        db.session.commit()
        institution_id, category_id = institution.id, category.id

    editor, verifier, citizen = app.test_client(), app.test_client(), app.test_client()
    for client, email in ((editor, "editor@example.com"), (verifier, "verifier@example.com")):
        client.post("/admin/login", data={"email": email, "password": PASSWORD})

    response = editor.post("/admin/services/new", data={
        "name": "Journey", "summary": "Example only", "institution_id": institution_id,
        "category_id": category_id, "delivery_mode": "",
    })
    manage = response.headers["Location"]
    editor.post(f"{manage}/fees/new", data={
        "fee_name": "Fee", "fee_kind": "official", "service_speed": "ordinary",
        "amount_ugx": "12345", "is_mandatory": "y",
    })
    editor.post("/admin/sources/new", data={
        "title": "Source", "url": "https://example.test/fee",
        "institution_id": institution_id, "source_type": "web_page",
    })

    page = citizen.get("/services/journey").get_data(as_text=True)
    assert "12,345" not in page and FEE_NOT_VERIFIED_MESSAGE in page

    review = {
        "status": "verified", "source_id": "1", "last_checked_on": TODAY.isoformat(),
        "review_due_on": FUTURE.isoformat(),
    }
    # The editor is refused, then the verifier succeeds.
    assert editor.post(f"{manage}/review/fees", data=review).status_code == 403
    assert verifier.post(f"{manage}/review/fees", data=review).status_code == 302
    assert "UGX 12,345" in citizen.get("/services/journey").get_data(as_text=True)

    # Any later edit hides the amount again until someone checks it.
    fee_id = "1"
    editor.post(f"{manage}/fees/{fee_id}/edit", data={
        "fee_name": "Fee", "fee_kind": "official", "service_speed": "ordinary",
        "amount_ugx": "99999", "is_mandatory": "y",
    })
    page = citizen.get("/services/journey").get_data(as_text=True)
    assert "99,999" not in page and "12,345" not in page

    with app.app_context():
        db.session.remove()
        db.drop_all()
