"""Turns records into plain dictionaries for the JSON API.

The API uses the same rules as the web pages. Fee amounts and payment details
come from build_checklist(), so an unverified fee is never sent. Administrator
names, contact details from reports and internal notes are never included.
"""

from app.logic.checklist import build_checklist, choose_variant
from app.logic.directory import INSTITUTION_TYPE_LABELS, record_status
from app.logic.search import MODE_LABELS
from app.logic.verification import STATUS_LABELS, overall_status


def iso(value):
    return value.isoformat() if value else None


def status_of(status):
    return {"status": status, "label": STATUS_LABELS[status]}


def service_summary(service):
    status = overall_status(service)
    return {
        "slug": service.slug,
        "name": service.name,
        "summary": service.summary,
        "institution": {"slug": service.institution.slug, "name": service.institution.name},
        "category": {"slug": service.category.slug, "name": service.category.name},
        "delivery_mode": service.delivery_mode,
        "delivery_mode_label": MODE_LABELS.get(service.delivery_mode, "Not confirmed"),
        "is_demonstration": service.is_demo,
        "verification": status_of(status),
    }


def source_data(source):
    if source is None:
        return None
    return {
        "title": source.title,
        "url": source.url,
        "institution": source.institution.name,
        "last_checked_on": iso(source.last_checked_on),
    }


def office_data(office):
    status = record_status(office)
    return {
        "id": office.id,
        "name": office.name,
        "institution": office.institution.name,
        "office_type": office.office_type,
        "address": office.physical_address,
        "district": office.district.name,
        "region": office.district.region.name,
        "phone": office.phone,
        "email": office.email,
        "website": office.website,
        "opening_hours": office.opening_hours,
        # Map-ready. Empty until confirmed.
        "location": (
            {"latitude": office.latitude, "longitude": office.longitude}
            if office.latitude is not None else None
        ),
        "is_demonstration": office.is_demo,
        "verification": {"status": status["status"], "label": status["label"]},
    }


def checklist_data(service, variant_id=None):
    """The full preparation checklist, in the structure from the project brief."""
    variant = choose_variant(service, variant_id)
    checklist = build_checklist(service, variant)
    sections = checklist["sections"]

    return {
        "service": {
            **service_summary(service),
            "description": service.description,
            "eligibility": service.eligibility,
            "online_url": service.online_url,
            "situation": variant.name if variant else None,
            "situations": [{"id": item.id, "name": item.name} for item in checklist["variants"]],
        },
        "steps": [
            {key: step[key] for key in ("number", "stage", "title", "instructions", "action_url")}
            for step in checklist["steps"]
        ],
        "documents": [
            {
                "name": item["name"],
                "required": item["is_mandatory"],
                "original": item["original"],
                "photocopies": item["photocopies"],
                "certified_copy": item["certified_copy"],
                "max_age_days": item["max_age_days"],
                "instructions": item["instructions"],
            }
            for item in checklist["documents"]
        ],
        "fees": [
            {
                "name": item["name"],
                "kind": item["kind"],
                "speed": item["speed"] or None,
                "required": item["is_mandatory"],
                # None unless verified. The message then explains why.
                "amount_ugx": item["amount_ugx"],
                "message": item["message"],
                "payment_method": item["payment_method"],
                "payment_instructions": item["payment_instructions"],
                "effective_from": iso(item["effective_from"]),
            }
            for item in checklist["fees"]
        ],
        "offices": [
            {
                **office_data(entry["office"]),
                "offers_this_service": status_of(entry["link_status"]),
                "note": entry["availability_note"],
            }
            for entry in checklist["offices"]
        ],
        "processing_time": [
            {key: item[key] for key in ("speed", "duration", "duration_note", "starts_after",
                                        "basis", "delay_factors")}
            for item in checklist["processing"]
        ],
        "sources": [source_data(source) for source in checklist["sources"]],
        "verification": {
            **status_of(checklist["status"]),
            "last_verified": iso(checklist["last_checked_on"]),
            "sections": {
                name: {
                    **status_of(section["status"]),
                    "last_checked_on": iso(section["last_checked_on"]),
                    "review_due_on": iso(section["review_due_on"]),
                }
                for name, section in sections.items()
            },
        },
    }


def institution_data(institution, detailed=False):
    status = record_status(institution)
    data = {
        "slug": institution.slug,
        "name": institution.name,
        "acronym": institution.acronym,
        "type": INSTITUTION_TYPE_LABELS[institution.institution_type],
        "website": institution.website,
        "is_demonstration": institution.is_demo,
        "verification": {"status": status["status"], "label": status["label"]},
    }
    if detailed:
        parent = institution.parent
        data.update({
            "description": institution.description,
            "phone": institution.phone,
            "email": institution.email,
            "headquarters": institution.headquarters,
            "parent": parent.slug if parent and not parent.is_archived else None,
            "source_url": institution.source_url,
            "last_verified_on": iso(institution.last_verified_on),
            "services": [
                service_summary(service)
                for service in sorted(institution.services, key=lambda s: s.name)
                if not service.is_archived
            ],
            "offices": [
                office_data(office) for office in institution.offices if not office.is_archived
            ],
        })
    return data
