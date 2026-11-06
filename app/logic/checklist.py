"""Builds the citizen preparation checklist for one service.

Every display rule lives here, so the web page and the future JSON API can't
disagree. The most important rule: a fee amount or payment instruction leaves
this module only if its section has been verified.
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.logic.search import MODE_LABELS
from app.logic.verification import (
    STATUS_LABELS,
    overall_status,
    section_statuses,
)
from app.models import GovernmentOffice, GovernmentService, ServiceOffice
from app.models.base import VERIFICATION_SECTIONS

FEE_NOT_VERIFIED_MESSAGE = (
    "Official fee not yet verified. Please confirm with the responsible agency."
)

# A fee's amount can be shown if it was verified, even if its review is overdue.
# Outdated amounts appear with a warning.
FEE_VISIBLE_STATUSES = ("verified", "outdated")

SPEED_LABELS = {"ordinary": "Ordinary", "express": "Express", "not_applicable": ""}
STARTS_AFTER_LABELS = {
    "submission": "Counted from submission",
    "payment": "Counted from payment",
    "approval": "Counted from approval",
    "unknown": "Start point not confirmed",
}
BASIS_LABELS = {
    "official_standard": "Official standard",
    "estimate": "Estimate",
    "unverified": "Unverified",
}
STAGE_LABELS = {
    "before_visit": "Before you go",
    "at_office": "At the office",
    "after_visit": "After your visit",
}

# Local offices come first, so nobody is sent to Kampala by default.
OFFICE_TYPE_ORDER = {
    "district": 0,
    "service_centre": 1,
    "regional": 2,
    "other": 3,
    "headquarters": 4,
}
NEARNESS_ORDER = {"district": 0, "region": 1, "other": 2}


def get_service(slug):
    """Find an available service with everything its checklist needs."""
    statement = (
        select(GovernmentService)
        .where(GovernmentService.slug == slug, GovernmentService.is_archived.is_(False))
        .options(
            selectinload(GovernmentService.institution),
            selectinload(GovernmentService.category),
            selectinload(GovernmentService.variants),
            selectinload(GovernmentService.documents),
            selectinload(GovernmentService.fees),
            selectinload(GovernmentService.processing),
            selectinload(GovernmentService.steps),
            selectinload(GovernmentService.verification_records),
            selectinload(GovernmentService.office_links)
            .selectinload(ServiceOffice.office)
            .selectinload(GovernmentOffice.district),
        )
    )
    return db.session.scalar(statement)


def choose_variant(service, variant_id=None):
    """Use the citizen's choice if it's valid, otherwise the default."""
    for variant in service.variants:
        if variant.id == variant_id:
            return variant
    for variant in service.variants:
        if variant.is_default:
            return variant
    return service.variants[0] if service.variants else None


def applies_to(item, variant):
    """An item with no variant applies to every case."""
    return item.variant_id is None or (variant is not None and item.variant_id == variant.id)


def yes_no(value, yes="Yes", no="No"):
    """Empty means nobody has confirmed it, which is different from "No"."""
    if value is None:
        return "Not confirmed"
    return yes if value else no


def describe_section(record, status):
    return {
        "status": status,
        "label": STATUS_LABELS[status],
        "last_checked_on": record.last_checked_on if record else None,
        "review_due_on": record.review_due_on if record else None,
        "source": record.source if record else None,
    }


def describe_document(document):
    return {
        "id": document.id,
        "name": document.name,
        "is_mandatory": document.is_mandatory,
        "original": yes_no(document.original_required, "Required", "Not required"),
        "photocopies": "Not confirmed" if document.photocopies is None else document.photocopies,
        "certified_copy": yes_no(document.certified_copy_accepted, "Accepted", "Not accepted"),
        "max_age_days": document.max_age_days,
        "instructions": document.instructions,
        "source": document.source,
    }


def describe_fee(fee, fees_status):
    """Leave out the amount and payment details unless they've been verified."""
    can_show = fees_status in FEE_VISIBLE_STATUSES and fee.amount_ugx is not None
    return {
        "name": fee.fee_name,
        "kind": fee.fee_kind,
        "speed": SPEED_LABELS[fee.service_speed],
        "is_mandatory": fee.is_mandatory,
        "amount_ugx": fee.amount_ugx if can_show else None,
        "message": None if can_show else FEE_NOT_VERIFIED_MESSAGE,
        "payment_method": fee.payment_method if can_show else None,
        "payment_instructions": fee.payment_instructions if can_show else None,
        "effective_from": fee.effective_from if can_show else None,
        "source": fee.source,
    }


def describe_duration(item):
    low, high = item.min_working_days, item.max_working_days
    if low is None and high is None:
        return "Not confirmed"
    if low is None:
        return f"Up to {high} working days"
    if high is None:
        return f"At least {low} working days"
    if low == high:
        return "1 working day" if low == 1 else f"{low} working days"
    return f"{low} to {high} working days"


def describe_processing(item):
    return {
        "speed": SPEED_LABELS[item.service_speed],
        "duration": describe_duration(item),
        "duration_note": item.duration_note,
        "starts_after": STARTS_AFTER_LABELS[item.starts_after],
        "basis": BASIS_LABELS[item.basis],
        "delay_factors": item.delay_factors,
        "source": item.source,
    }


def describe_step(step):
    return {
        "number": step.step_number,
        "stage": STAGE_LABELS[step.stage],
        "title": step.title,
        "instructions": step.instructions,
        "action_url": step.action_url,
        "source": step.source,
    }


def nearness(office, district_id, region_id):
    """How close an office is to the place the citizen chose."""
    if district_id and office.district_id == district_id:
        return "district"
    if region_id and office.district.region_id == region_id:
        return "region"
    return "other"


def list_offices(service, district=None, region_id=None):
    """Open offices for a service, closest first and local before headquarters."""
    district_id = district.id if district else None
    chosen_region = district.region_id if district else region_id

    entries = []
    for link in service.office_links:
        office = link.office
        if office.is_archived:
            continue
        entries.append({
            "office": office,
            "link_status": link.verification_status,
            "link_label": STATUS_LABELS[link.verification_status],
            "availability_note": link.availability_note,
            "nearness": nearness(office, district_id, chosen_region),
            "source": link.source,
        })

    entries.sort(key=lambda entry: (
        NEARNESS_ORDER[entry["nearness"]],
        OFFICE_TYPE_ORDER[entry["office"].office_type],
        entry["office"].name.lower(),
    ))
    return entries


def collect_sources(*groups):
    """Every source used on this checklist, listed once."""
    sources = {}
    for group in groups:
        for item in group:
            source = item["source"]
            if source is not None:
                sources[source.id] = source
    return sorted(sources.values(), key=lambda source: source.title.lower())


def overall_last_checked(sections):
    """The oldest check date, shown only once every section has been checked.

    Showing the newest date would make a partly checked service look current.
    """
    dates = [section["last_checked_on"] for section in sections.values()]
    return None if None in dates else min(dates)


def build_checklist(service, variant=None, district=None, region_id=None, today=None):
    """Put together everything shown on the preparation page."""
    today = today or date.today()
    statuses = section_statuses(service, today)
    records = {record.section: record for record in service.verification_records}
    sections = {
        section: describe_section(records.get(section), statuses[section])
        for section in VERIFICATION_SECTIONS
    }

    documents = [
        describe_document(item) for item in service.documents if applies_to(item, variant)
    ]
    fees = [
        describe_fee(item, statuses["fees"]) for item in service.fees if applies_to(item, variant)
    ]
    processing = [
        describe_processing(item) for item in service.processing if applies_to(item, variant)
    ]
    steps = [describe_step(item) for item in service.steps if applies_to(item, variant)]
    offices = list_offices(service, district, region_id)

    place_chosen = district is not None or region_id is not None
    has_nearby = any(entry["nearness"] != "other" for entry in offices)
    status = overall_status(service, today)

    return {
        "service": service,
        "variant": variant,
        "variants": service.variants,
        "delivery_mode": MODE_LABELS.get(service.delivery_mode, "Not confirmed"),
        "status": status,
        "status_label": STATUS_LABELS[status],
        "last_checked_on": overall_last_checked(sections),
        "sections": sections,
        "documents": documents,
        "required_documents": [item for item in documents if item["is_mandatory"]],
        "optional_documents": [item for item in documents if not item["is_mandatory"]],
        "fees": fees,
        "fee_message": FEE_NOT_VERIFIED_MESSAGE,
        "processing": processing,
        "steps": steps,
        "offices": offices,
        "no_nearby_office": place_chosen and not has_nearby,
        "sources": collect_sources(
            sections.values(), documents, fees, processing, steps, offices
        ),
    }
