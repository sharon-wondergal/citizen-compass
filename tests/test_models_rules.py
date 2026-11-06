"""Proves the design's rules work through the models.

Each "refused" test checks the name of the rule that fired, so a test can't
pass because a different rule happened to refuse the data.
"""

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import (
    CitizenReport,
    DailyView,
    District,
    GovernmentInstitution,
    GovernmentService,
    OfficialSource,
    ProcessingInformation,
    RequiredDocument,
    SearchLog,
    ServiceFee,
    ServiceOffice,
    ServiceStep,
    ServiceVariant,
    VerificationRecord,
)


def refused(database, message_part):
    """Commit, and require the database to refuse with the expected rule."""
    with pytest.raises(IntegrityError) as caught:
        database.session.commit()
    database.session.rollback()
    assert message_part in str(caught.value.orig)


def fees_record(sample, **values):
    return VerificationRecord(
        service=sample.service, section="fees", last_edited_by=sample.editor, **values
    )


def evidence(sample):
    return {
        "source": sample.source,
        "last_checked_on": sample.today,
        "review_due_on": sample.review_date,
    }


# ---------- Relationships ----------

def test_service_reaches_its_institution_and_category(sample):
    assert sample.service.institution.name == "Example Agency"
    assert sample.service.category.name == "Example Category"
    assert sample.service in sample.institution.services


def test_office_reaches_its_region_through_its_district(sample):
    assert sample.office.district.region.name == "Example Region"


def test_new_records_start_as_pending(database, sample):
    record = fees_record(sample)
    database.session.add(record)
    database.session.commit()

    assert record.status == "pending"
    assert sample.office.verification_status == "pending"
    assert sample.institution.verification_status == "pending"


def test_service_lists_are_sorted(database, sample):
    sample.service.steps = [
        ServiceStep(step_number=2, title="Second"),
        ServiceStep(step_number=1, title="First"),
    ]
    database.session.commit()
    database.session.expire_all()

    assert [step.title for step in sample.service.steps] == ["First", "Second"]


def test_one_source_can_support_many_items(database, sample):
    database.session.add_all([
        RequiredDocument(service=sample.service, name="Example", source=sample.source),
        ServiceFee(service=sample.service, fee_name="Example", source=sample.source),
    ])
    database.session.commit()

    assert sample.service.documents[0].source is sample.service.fees[0].source


def test_service_and_office_link_in_both_directions(database, sample):
    link = ServiceOffice(service=sample.service, office=sample.office)
    database.session.add(link)
    database.session.commit()

    assert sample.service.office_links[0].office is sample.office
    assert sample.office.service_links[0].service is sample.service


def test_institution_has_a_parent_ministry(database, sample):
    child = GovernmentInstitution(name="Child Agency", slug="child", parent=sample.institution)
    database.session.add(child)
    database.session.commit()

    assert child in sample.institution.children


# ---------- Verification ----------

def test_verified_needs_evidence(database, sample):
    database.session.add(fees_record(sample, status="verified"))
    refused(database, "ck_verification_records_verified_needs_evidence")


def test_last_editor_cannot_verify_their_own_change(database, sample):
    database.session.add(
        fees_record(sample, status="verified", verified_by=sample.editor, **evidence(sample))
    )
    refused(database, "ck_verification_records_separate_approval")


def test_different_person_can_verify(database, sample):
    record = fees_record(
        sample, status="verified", verified_by=sample.verifier, **evidence(sample)
    )
    database.session.add(record)
    database.session.commit()

    assert record.verified_by is sample.verifier


def test_one_record_per_section(database, sample):
    database.session.add_all([fees_record(sample), fees_record(sample)])
    refused(database, "verification_records.service_id, verification_records.section")


def test_unknown_section_is_refused(database, sample):
    database.session.add(VerificationRecord(service=sample.service, section="gossip"))
    refused(database, "ck_verification_records_section_valid")


def test_demo_office_can_never_be_verified(database, sample):
    sample.office.verification_status = "verified"
    sample.office.source = sample.source
    sample.office.last_verified_on = sample.today
    sample.office.review_due_on = sample.review_date
    sample.office.verified_by = sample.verifier
    refused(database, "ck_government_offices_demo_never_verified")


def test_demo_institution_can_never_be_verified(database, sample):
    sample.institution.verification_status = "verified"
    sample.institution.source_url = "https://example.test/source"
    sample.institution.last_verified_on = sample.today
    sample.institution.review_due_on = sample.review_date
    sample.institution.verified_by = sample.verifier
    refused(database, "ck_government_institutions_demo_never_verified")


def test_office_link_needs_evidence_to_be_verified(database, sample):
    database.session.add(
        ServiceOffice(service=sample.service, office=sample.office, verification_status="verified")
    )
    refused(database, "ck_service_offices_verified_needs_evidence")


def test_same_office_cannot_be_linked_twice(database, sample):
    database.session.add_all([
        ServiceOffice(service=sample.service, office=sample.office),
        ServiceOffice(service=sample.service, office=sample.office),
    ])
    refused(database, "service_offices.service_id, service_offices.office_id")


# ---------- Fees, documents and processing ----------

def test_unknown_fee_and_free_fee_stay_different(database, sample):
    unknown = ServiceFee(service=sample.service, fee_name="Unknown", amount_ugx=None)
    free = ServiceFee(service=sample.service, fee_name="Free", amount_ugx=0)
    database.session.add_all([unknown, free])
    database.session.commit()

    assert unknown.amount_ugx is None
    assert free.amount_ugx == 0


def test_negative_fee_is_refused(database, sample):
    database.session.add(ServiceFee(service=sample.service, fee_name="Bad", amount_ugx=-1))
    refused(database, "ck_service_fees_amount_ugx_minimum")


def test_unconfirmed_document_details_stay_empty(database, sample):
    document = RequiredDocument(service=sample.service, name="Example")
    database.session.add(document)
    database.session.commit()

    assert document.is_mandatory is True
    assert document.original_required is None
    assert document.photocopies is None


def test_document_age_must_be_positive(database, sample):
    database.session.add(RequiredDocument(service=sample.service, name="Bad", max_age_days=0))
    refused(database, "ck_required_documents_max_age_days_minimum")


def test_processing_days_must_be_in_order(database, sample):
    database.session.add(ProcessingInformation(
        service=sample.service, min_working_days=10, max_working_days=5
    ))
    refused(database, "ck_processing_information_days_in_order")


def test_processing_defaults_claim_nothing(database, sample):
    processing = ProcessingInformation(service=sample.service)
    database.session.add(processing)
    database.session.commit()

    assert processing.basis == "unverified"
    assert processing.starts_after == "unknown"


# ---------- Input safety ----------

@pytest.mark.parametrize("bad_link", ["javascript:alert(1)", "ftp://example.test", "example.test"])
def test_source_must_be_a_web_link(database, sample, bad_link):
    database.session.add(OfficialSource(institution=sample.institution, title="Bad", url=bad_link))
    refused(database, "ck_official_sources_url_is_web_link")


def test_service_portal_must_be_a_web_link(database, sample):
    sample.service.online_url = "javascript:alert(1)"
    refused(database, "ck_government_services_online_url_is_web_link")


def test_coordinates_must_come_together(database, sample):
    sample.office.latitude = 2.0
    refused(database, "ck_government_offices_coordinates_together")


def test_latitude_must_be_on_earth(database, sample):
    sample.office.latitude = 95.0
    sample.office.longitude = 32.0
    refused(database, "ck_government_offices_latitude_range")


# ---------- Citizen data ----------

def example_report(code, **values):
    return CitizenReport(
        reference_code=code,
        service_name="Example Service",
        problem_type="incorrect_fee",
        description=values.pop("description", "The example fee looks wrong."),
        **values,
    )


def test_citizen_can_report_without_contact_details(database, sample):
    report = example_report("CC-0001")
    database.session.add(report)
    database.session.commit()

    assert report.status == "new"
    assert report.contact_info is None
    assert report.submitted_at is not None


def test_report_cannot_close_without_action(database, sample):
    database.session.add(example_report("CC-0002", status="resolved"))
    refused(database, "ck_citizen_reports_closed_needs_action")


def test_very_short_report_is_refused(database, sample):
    database.session.add(example_report("CC-0003", description="Bad"))
    refused(database, "ck_citizen_reports_description_length")


def test_daily_view_counts_one_thing(database, sample):
    database.session.add(DailyView(
        view_date=date(2026, 1, 1), service_id=sample.service.id,
        institution_id=sample.institution.id,
    ))
    refused(database, "ck_daily_views_counts_one_thing")


def test_one_view_row_per_service_per_day(database, sample):
    database.session.add_all([
        DailyView(view_date=date(2026, 1, 1), service_id=sample.service.id),
        DailyView(view_date=date(2026, 1, 1), service_id=sample.service.id),
    ])
    refused(database, "daily_views.view_date, daily_views.service_id")


# ---------- Delete rules ----------

def test_source_in_use_cannot_be_deleted(database, sample):
    database.session.add(
        RequiredDocument(service=sample.service, name="Example", source=sample.source)
    )
    database.session.commit()
    database.session.delete(sample.source)
    refused(database, "FOREIGN KEY")


def test_region_with_districts_cannot_be_deleted(database, sample):
    database.session.delete(sample.region)
    refused(database, "FOREIGN KEY")


def test_district_with_offices_cannot_be_deleted(database, sample):
    database.session.delete(sample.district)
    refused(database, "FOREIGN KEY")


def test_institution_with_services_cannot_be_deleted(database, sample):
    database.session.delete(sample.institution)
    refused(database, "FOREIGN KEY")


def test_category_with_services_cannot_be_deleted(database, sample):
    database.session.delete(sample.category)
    refused(database, "FOREIGN KEY")


def test_admin_with_history_cannot_be_deleted(database, sample):
    database.session.add(fees_record(sample))
    database.session.commit()
    database.session.delete(sample.editor)
    refused(database, "FOREIGN KEY")


def test_deleting_a_service_removes_its_details_only(database, sample):
    service_id = sample.service.id
    sample.service.documents.append(RequiredDocument(name="Example", source=sample.source))
    sample.service.variants.append(ServiceVariant(name="Example"))
    sample.service.office_links.append(ServiceOffice(office=sample.office))
    database.session.add(example_report("CC-0004", service=sample.service))
    database.session.add(SearchLog(query_text="example", results_count=1,
                                   top_service_id=service_id))
    database.session.commit()

    database.session.delete(sample.service)
    database.session.commit()
    database.session.expire_all()

    assert database.session.query(RequiredDocument).count() == 0
    assert database.session.query(ServiceVariant).count() == 0
    assert database.session.query(ServiceOffice).count() == 0
    assert database.session.query(District).count() == 1
    assert database.session.query(OfficialSource).count() == 1

    report = database.session.query(CitizenReport).one()
    assert report.service_id is None
    assert report.service_name == "Example Service"
    assert database.session.query(SearchLog).one().top_service_id is None


def test_deleting_a_variant_removes_only_its_own_items(database, sample):
    variant = ServiceVariant(service=sample.service, name="Lost")
    database.session.add_all([
        RequiredDocument(service=sample.service, variant=variant, name="Variant document"),
        RequiredDocument(service=sample.service, name="Shared document"),
    ])
    database.session.commit()

    database.session.delete(variant)
    database.session.commit()
    database.session.expire_all()

    assert [item.name for item in sample.service.documents] == ["Shared document"]


def test_service_with_the_same_name_needs_another_institution(database, sample):
    database.session.add(GovernmentService(
        institution=sample.institution, category=sample.category,
        name="Example Service", slug="another-slug", summary="Example only",
    ))
    refused(database, "government_services.institution_id, government_services.name")
