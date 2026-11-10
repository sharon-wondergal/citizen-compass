"""Stage 13 tests: the read-only JSON API. All data here is invented.

Numbers such as 12345 are not real fees.
"""

from datetime import date, timedelta

import pytest

from app import create_app
from app.config import TestingConfig
from app.extensions import db
from app.logic.verification import create_verification_records
from app.models import (
    CitizenReport,
    ProcessingInformation,
    RequiredDocument,
    ServiceFee,
    ServiceOffice,
    ServiceVariant,
)


def get_json(client, address, status=200):
    response = client.get(address)
    assert response.status_code == status, response.get_data(as_text=True)
    assert response.is_json
    return response.get_json()


@pytest.fixture
def world(sample):
    service = sample.service
    service.is_demo = False
    create_verification_records(service)
    sample.lost = ServiceVariant(service=service, name="Lost", is_default=False)
    db.session.add_all([
        sample.lost,
        RequiredDocument(service=service, name="Shared paper"),
        RequiredDocument(service=service, variant=sample.lost, name="Police letter"),
        ServiceFee(service=service, fee_name="Test fee", amount_ugx=12345,
                   payment_method="Secret method"),
        ProcessingInformation(service=service, min_working_days=2, max_working_days=4),
        ServiceOffice(service=service, office=sample.office),
    ])
    db.session.commit()
    return sample


def verify_fees(data):
    for record in data.service.verification_records:
        if record.section == "fees":
            record.status = "verified"
            record.source = data.source
            record.last_checked_on = date.today()
            record.review_due_on = date.today() + timedelta(days=90)
            record.verified_by = data.verifier
    db.session.commit()


# ---------- The index ----------

def test_index_lists_endpoints_and_a_notice(client, database):
    data = get_json(client, "/api/v1")
    assert "services" in data["endpoints"]
    assert "not a government service" in data["notice"]


# ---------- Services ----------

def test_services_list_with_paging(client, world):
    data = get_json(client, "/api/v1/services")
    assert data["meta"] == {"page": 1, "pages": 1, "total": 1, "per_page": 10}
    item = data["data"][0]
    assert item["slug"] == "example-service"
    assert item["institution"]["name"] == "Example Agency"
    assert item["verification"]["status"] == "pending"


def test_services_can_be_searched_and_filtered(client, world):
    assert get_json(client, "/api/v1/services?q=example")["meta"]["total"] == 1
    assert get_json(client, "/api/v1/services?q=zzzz")["meta"]["total"] == 0
    assert get_json(client, "/api/v1/services?category=example-category")["meta"]["total"] == 1
    assert get_json(client, "/api/v1/services?status=verified")["meta"]["total"] == 0


@pytest.mark.parametrize("address, message", [
    ("/api/v1/services?category=nope", "Unknown value for 'category'."),
    ("/api/v1/services?mode=teleport", "Unknown value for 'mode'."),
    ("/api/v1/services?status=approved", "Unknown value for 'status'."),
    ("/api/v1/services?district=abc", "Unknown value for 'district'."),
    ("/api/v1/services?page=0", "'page' must be a whole number of 1 or more."),
    ("/api/v1/services?page=abc", "'page' must be a whole number of 1 or more."),
    ("/api/v1/services?admin=1", "Unknown parameter: admin."),
])
def test_bad_requests_are_explained(client, world, address, message):
    data = get_json(client, address, status=400)
    assert data["error"]["message"] == message


def test_api_searches_are_not_logged(client, world):
    from app.models import SearchLog

    get_json(client, "/api/v1/services?q=example")
    assert db.session.query(SearchLog).count() == 0


def test_single_service(client, world):
    data = get_json(client, "/api/v1/services/example-service")["data"]
    assert data["name"] == "Example Service"
    assert data["checklist"] == "/api/v1/services/example-service/checklist"


def test_unknown_service_is_a_json_404(client, world):
    data = get_json(client, "/api/v1/services/no-such-service", status=404)
    assert data["error"]["code"] == "not_found"


def test_archived_service_is_hidden(client, world):
    world.service.is_archived = True
    db.session.commit()
    get_json(client, "/api/v1/services/example-service", status=404)
    assert get_json(client, "/api/v1/services")["meta"]["total"] == 0


# ---------- Checklists ----------

def test_checklist_has_the_brief_structure(client, world):
    data = get_json(client, "/api/v1/services/example-service/checklist")["data"]
    for key in ("service", "documents", "fees", "offices", "processing_time", "sources",
                "verification"):
        assert key in data
    assert data["verification"]["status"] == "pending"
    assert data["verification"]["last_verified"] is None
    assert data["processing_time"][0]["duration"] == "2 to 4 working days"


def test_unverified_fee_is_never_sent(client, world):
    response = client.get("/api/v1/services/example-service/checklist")
    text = response.get_data(as_text=True)
    fee = response.get_json()["data"]["fees"][0]

    assert fee["amount_ugx"] is None
    assert fee["message"].startswith("Official fee not yet verified")
    assert "12345" not in text
    assert "Secret method" not in text


def test_verified_fee_is_sent(client, world):
    verify_fees(world)
    fee = get_json(client, "/api/v1/services/example-service/checklist")["data"]["fees"][0]
    assert fee["amount_ugx"] == 12345
    assert fee["payment_method"] == "Secret method"


def test_situation_changes_the_documents(client, world):
    shared = get_json(client, "/api/v1/services/example-service/checklist")["data"]
    lost = get_json(
        client, f"/api/v1/services/example-service/checklist?situation={world.lost.id}"
    )["data"]

    assert [d["name"] for d in lost["documents"]] == ["Shared paper", "Police letter"]
    assert lost["service"]["situation"] == "Lost"
    assert len(shared["service"]["situations"]) == 1


def test_unknown_situation_is_refused(client, world):
    data = get_json(client, "/api/v1/services/example-service/checklist?situation=999", 400)
    assert data["error"]["message"] == "Unknown value for 'situation'."


def test_office_details_are_map_ready_and_honest(client, world):
    office = get_json(client, "/api/v1/services/example-service/checklist")["data"]["offices"][0]
    assert office["address"] is None
    assert office["location"] is None
    assert office["offers_this_service"]["status"] == "pending"


def test_private_details_are_never_included(client, world):
    db.session.add(CitizenReport(
        reference_code="CC-1", service=world.service, service_name="Example Service",
        problem_type="other", description="A private report text.", contact_info="0700 000000",
    ))
    record = world.service.verification_records[0]
    record.notes = "Internal note"
    db.session.commit()

    text = client.get("/api/v1/services/example-service/checklist").get_data(as_text=True)
    for private in ("0700 000000", "A private report text.", "Internal note",
                    "Example Verifier", "Example Editor", "verifier@example.test"):
        assert private not in text


# ---------- Institutions, offices and categories ----------

def test_institutions_list_and_detail(client, world):
    listing = get_json(client, "/api/v1/institutions")
    assert listing["data"][0]["slug"] == "example-agency"

    detail = get_json(client, "/api/v1/institutions/example-agency")["data"]
    assert detail["services"][0]["slug"] == "example-service"
    assert detail["offices"][0]["name"] == "Example Office"


def test_institution_filters_are_checked(client, world):
    get_json(client, "/api/v1/institutions?type=alien", status=400)
    get_json(client, "/api/v1/institutions/nobody", status=404)


def test_offices_can_be_filtered(client, world):
    data = get_json(client, f"/api/v1/offices?district={world.district.id}")
    assert data["meta"]["total"] == 1
    assert data["meta"]["no_office_in_district"] is None
    get_json(client, "/api/v1/offices?district=999999", status=400)


def test_categories_include_service_counts(client, world):
    data = get_json(client, "/api/v1/categories")["data"]
    assert data == [{"slug": "example-category", "name": "Example Category", "services": 1}]


# ---------- Safety ----------

def test_api_cannot_change_anything(client, world):
    for method in ("post", "put", "patch", "delete"):
        response = getattr(client, method)("/api/v1/services")
        assert response.status_code == 405
        assert response.is_json


def test_unknown_api_address_is_a_json_404(client, database):
    assert get_json(client, "/api/v1/secrets", status=404)["error"]["code"] == "not_found"


def test_website_errors_stay_as_pages(client, database):
    response = client.get("/no-such-page")
    assert response.status_code == 404
    assert not response.is_json


def test_admin_functions_are_not_in_the_api(client, database):
    for address in ("/api/v1/admin", "/api/v1/reports", "/api/v1/history"):
        assert client.get(address).status_code == 404


def test_api_is_rate_limited(monkeypatch):
    monkeypatch.setattr(TestingConfig, "RATELIMIT_ENABLED", True)
    limited_app = create_app("testing")
    with limited_app.app_context():
        db.create_all()
    client = limited_app.test_client()
    statuses = [client.get("/api/v1/categories").status_code for _ in range(121)]
    last = client.get("/api/v1/categories")
    with limited_app.app_context():
        db.session.remove()
        db.drop_all()

    assert statuses[:120] == [200] * 120
    assert last.status_code == 429
    assert last.get_json()["error"]["code"] == "too_many_requests"
