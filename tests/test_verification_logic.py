"""Tests for the status citizens see."""

from datetime import date, timedelta

from app.logic.verification import STATUS_LABELS, effective_status, overall_status
from app.models import VerificationRecord
from app.models.base import VERIFICATION_SECTIONS, VERIFICATION_STATUSES

TODAY = date(2026, 6, 1)
YESTERDAY = TODAY - timedelta(days=1)
TOMORROW = TODAY + timedelta(days=1)


def records(service, **statuses):
    """Build one in-memory record per section, verified unless stated."""
    service.is_demo = False
    service.verification_records = [
        VerificationRecord(
            section=section,
            status=statuses.get(section, "verified"),
            review_due_on=TOMORROW,
        )
        for section in VERIFICATION_SECTIONS
    ]


def test_every_status_has_a_label():
    assert set(STATUS_LABELS) == set(VERIFICATION_STATUSES)


def test_verified_stays_verified_until_the_review_date():
    assert effective_status("verified", TODAY, TODAY) == "verified"
    assert effective_status("verified", TOMORROW, TODAY) == "verified"


def test_verified_becomes_outdated_after_the_review_date():
    assert effective_status("verified", YESTERDAY, TODAY) == "outdated"


def test_review_date_never_upgrades_other_statuses():
    assert effective_status("pending", YESTERDAY, TODAY) == "pending"
    assert effective_status("unavailable", YESTERDAY, TODAY) == "unavailable"


def test_service_with_no_records_is_pending(sample):
    assert overall_status(sample.service, TODAY) == "pending"


def test_missing_section_stops_a_service_being_verified(sample):
    records(sample.service)
    sample.service.verification_records.pop()
    assert overall_status(sample.service, TODAY) == "pending"


def test_all_sections_verified_makes_the_service_verified(sample):
    records(sample.service)
    assert overall_status(sample.service, TODAY) == "verified"


def test_demo_service_can_never_count_as_verified(sample):
    records(sample.service)
    sample.service.is_demo = True
    assert overall_status(sample.service, TODAY) == "pending"


def test_one_pending_section_makes_the_service_pending(sample):
    records(sample.service, processing="pending")
    assert overall_status(sample.service, TODAY) == "pending"


def test_expired_section_makes_the_service_outdated(sample):
    records(sample.service)
    sample.service.verification_records[0].review_due_on = YESTERDAY
    assert overall_status(sample.service, TODAY) == "outdated"


def test_unavailable_is_the_weakest_status(sample):
    records(sample.service, fees="unavailable", documents="outdated", offices="pending")
    assert overall_status(sample.service, TODAY) == "unavailable"
