"""The short answer shown on the homepage after someone asks about a service.

It's built from build_checklist(), so every checklist rule still applies. In
particular, a fee amount appears here only if it has been verified.
"""

from flask import url_for

from app.logic.checklist import build_checklist, choose_variant, get_service
from app.logic.search import SearchFilters, log_search, run_search, spelling_suggestion
from app.template_helpers import ugx


def describe_fees(checklist):
    """Verified amounts, or the standard "not yet verified" message."""
    amounts = [
        f"{fee['speed']}: {ugx(fee['amount_ugx'])}" if fee["speed"] else ugx(fee["amount_ugx"])
        for fee in checklist["fees"]
        if fee["amount_ugx"] is not None
    ]
    return ", ".join(amounts) if amounts else checklist["fee_message"]


def describe_documents(checklist):
    names = [document["name"] for document in checklist["required_documents"]]
    return ", ".join(names) if names else "No document list has been added yet."


def describe_office(checklist):
    if not checklist["offices"]:
        return "No offices have been listed for this service yet."
    first = checklist["offices"][0]["office"]
    others = len(checklist["offices"]) - 1
    return f"{first.name} and {others} more" if others else first.name


def describe_time(checklist):
    if not checklist["processing"]:
        return "Not confirmed"
    item = checklist["processing"][0]
    return f"{item['duration']} ({item['basis']})"


def build_answer(service):
    variant = choose_variant(service)
    checklist = build_checklist(service, variant)
    institution = service.institution
    return {
        "found": True,
        "name": service.name,
        "agency": institution.acronym or institution.name,
        "is_demo": service.is_demo,
        "status": checklist["status"],
        "status_label": checklist["status_label"],
        "documents": describe_documents(checklist),
        "fee": describe_fees(checklist),
        "office": describe_office(checklist),
        "time": describe_time(checklist),
        "checklist_url": url_for("services.detail", slug=service.slug),
        "website": institution.website,
    }


def find_answer(query):
    """Answer a question with its best matching service."""
    filters = SearchFilters(query=query)
    results = run_search(filters)
    log_search(filters, results)

    if not results.items:
        return {"found": False, "query": query, "suggestion": spelling_suggestion(query)}

    # Reload with everything the checklist needs. The search only loads a summary.
    return build_answer(get_service(results.items[0]["service"].slug))
