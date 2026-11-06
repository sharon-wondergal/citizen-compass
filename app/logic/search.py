"""Finding government services.

The text search and most filters run in the database. The verification filter
runs in Python, because "outdated" depends on today's date and every section of
a service. That's fine for hundreds of services. Search would need revisiting
for many thousands.
"""

import difflib
import math
import re
from dataclasses import dataclass

from flask import current_app
from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload, selectinload

from app.extensions import db
from app.logic.verification import STATUS_LABELS, overall_status
from app.models import (
    District,
    GovernmentInstitution,
    GovernmentOffice,
    GovernmentService,
    Region,
    SearchLog,
    ServiceCategory,
    ServiceOffice,
)

MAX_QUERY_LENGTH = 100
MAX_SEARCH_WORDS = 8
RESULTS_PER_PAGE = 10
MINIMUM_SUGGESTION_LENGTH = 2
SUGGESTION_LIMIT = 6

MODE_LABELS = {
    "online": "Online",
    "physical": "In person",
    "hybrid": "Online and in person",
}

# Common words that would stop "how to get a passport" from matching "passport".
STOP_WORDS = {
    "a", "an", "and", "apply", "for", "get", "how", "i", "in", "my", "of", "on", "the", "to",
}

# Removed before a search is saved, in case someone types personal details:
# email addresses, long mixed letters and numbers (such as ID numbers),
# and long numbers (such as phone numbers).
SENSITIVE_TEXT = re.compile(
    r"\S+@\S+"
    r"|\b(?=[A-Za-z0-9]*\d)[A-Za-z0-9]{10,}\b"
    r"|\d[\d\s-]{4,}\d"
)


@dataclass
class SearchFilters:
    query: str = ""
    category: str = ""
    institution: str = ""
    region: int | None = None
    district: int | None = None
    mode: str = ""
    status: str = ""
    page: int = 1

    @property
    def has_filters(self):
        return bool(
            self.category or self.institution or self.region
            or self.district or self.mode or self.status
        )

    def as_url_values(self):
        """The active search as web address values, without the page number."""
        values = {
            "q": self.query,
            "category": self.category,
            "institution": self.institution,
            "region": self.region,
            "district": self.district,
            "mode": self.mode,
            "status": self.status,
        }
        return {name: value for name, value in values.items() if value}


@dataclass
class SearchResults:
    items: list
    total: int
    page: int
    pages: int


def paginate(items, page):
    """Return one page of a list. A page past the end shows the last page."""
    total = len(items)
    pages = max(math.ceil(total / RESULTS_PER_PAGE), 1)
    page = min(page, pages)
    start = (page - 1) * RESULTS_PER_PAGE
    return SearchResults(
        items=items[start:start + RESULTS_PER_PAGE], total=total, page=page, pages=pages
    )


# ---------- Reading the request ----------

def clean_query(raw_text):
    """Tidy search text: remove control characters, extra spaces and excess length."""
    printable = "".join(character if character.isprintable() else " " for character in raw_text)
    return " ".join(printable.split())[:MAX_QUERY_LENGTH].strip()


def filter_options():
    """The choices shown in the filter menus."""
    return {
        "categories": db.session.scalars(
            select(ServiceCategory)
            .where(ServiceCategory.is_active.is_(True))
            .order_by(ServiceCategory.display_order, ServiceCategory.name)
        ).all(),
        "institutions": db.session.scalars(
            select(GovernmentInstitution)
            .where(GovernmentInstitution.is_archived.is_(False))
            .order_by(GovernmentInstitution.name)
        ).all(),
        "regions": db.session.scalars(select(Region).order_by(Region.name)).all(),
        "districts": db.session.scalars(select(District).order_by(District.name)).all(),
        "modes": MODE_LABELS,
        "statuses": STATUS_LABELS,
    }


def parse_filters(args, options):
    """Turn web address values into filters.

    Anyone can edit a web address, so each value is checked against the real
    choices. An unknown value is ignored, and the page shows "All" for it.
    """

    def known(value, allowed):
        return value if value in allowed else ""

    def known_id(value, records):
        return value if value in {record.id for record in records} else None

    return SearchFilters(
        query=clean_query(args.get("q", "")),
        category=known(args.get("category", ""), {c.slug for c in options["categories"]}),
        institution=known(args.get("institution", ""), {i.slug for i in options["institutions"]}),
        region=known_id(args.get("region", type=int), options["regions"]),
        district=known_id(args.get("district", type=int), options["districts"]),
        mode=known(args.get("mode", ""), options["modes"]),
        status=known(args.get("status", ""), options["statuses"]),
        page=max(args.get("page", default=1, type=int) or 1, 1),
    )


# ---------- Searching ----------

def search_words(query):
    """Split a query into useful words, without common words or plural endings."""
    words = query.lower().split()
    useful = [word for word in words if word not in STOP_WORDS] or words
    singular = [word[:-1] if word.endswith("s") and len(word) > 3 else word for word in useful]
    return singular[:MAX_SEARCH_WORDS]


def like_pattern(word):
    """Make a LIKE pattern. % and _ in the search are treated as plain text."""
    escaped = word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def word_condition(word):
    """A service matches a word if the word appears in any of these columns."""
    pattern = like_pattern(word)
    columns = (
        GovernmentService.name,
        GovernmentService.summary,
        GovernmentService.description,
        GovernmentService.keywords,
        GovernmentInstitution.name,
        GovernmentInstitution.acronym,
        ServiceCategory.name,
    )
    return or_(*(column.ilike(pattern, escape="\\") for column in columns))


def services_in_location(filters):
    """The ids of services linked to an open office in the chosen place."""
    statement = (
        select(ServiceOffice.service_id)
        .join(GovernmentOffice, ServiceOffice.office_id == GovernmentOffice.id)
        .join(District, GovernmentOffice.district_id == District.id)
        .where(GovernmentOffice.is_archived.is_(False))
    )
    if filters.district:
        statement = statement.where(District.id == filters.district)
    if filters.region:
        statement = statement.where(District.region_id == filters.region)
    return statement


def matching_services(filters):
    statement = (
        select(GovernmentService)
        .join(GovernmentService.institution)
        .join(GovernmentService.category)
        .where(GovernmentService.is_archived.is_(False))
        .options(
            joinedload(GovernmentService.institution),
            joinedload(GovernmentService.category),
            selectinload(GovernmentService.verification_records),
        )
    )
    for word in search_words(filters.query):
        statement = statement.where(word_condition(word))
    if filters.category:
        statement = statement.where(ServiceCategory.slug == filters.category)
    if filters.institution:
        statement = statement.where(GovernmentInstitution.slug == filters.institution)
    if filters.mode:
        statement = statement.where(GovernmentService.delivery_mode == filters.mode)
    if filters.region or filters.district:
        statement = statement.where(GovernmentService.id.in_(services_in_location(filters)))
    return db.session.scalars(statement).unique().all()


def relevance(service, words):
    """Higher is better. A match in the service's name matters most."""
    name = service.name.lower()
    keywords = (service.keywords or "").lower()
    score = 0
    for word in words:
        if word in name:
            score += 3
        if word in keywords:
            score += 2
    return score


def run_search(filters):
    words = search_words(filters.query)
    services = sorted(
        matching_services(filters),
        key=lambda service: (-relevance(service, words), service.name.lower()),
    )
    items = [{"service": service, "status": overall_status(service)} for service in services]
    if filters.status:
        items = [item for item in items if item["status"] == filters.status]

    return paginate(items, filters.page)


# ---------- Suggestions ----------

def suggest_services(text):
    """Service names for the search box, as someone types."""
    query = clean_query(text)
    if len(query) < MINIMUM_SUGGESTION_LENGTH:
        return []
    pattern = like_pattern(query.lower())
    statement = (
        select(GovernmentService.name)
        .where(
            GovernmentService.is_archived.is_(False),
            or_(
                GovernmentService.name.ilike(pattern, escape="\\"),
                GovernmentService.keywords.ilike(pattern, escape="\\"),
            ),
        )
        .order_by(GovernmentService.name)
        .limit(SUGGESTION_LIMIT)
    )
    return db.session.scalars(statement).all()


def spelling_suggestion(query):
    """Offer a corrected search when a word is close to one we know."""
    rows = db.session.execute(
        select(GovernmentService.name, GovernmentService.keywords)
        .where(GovernmentService.is_archived.is_(False))
    ).all()
    known_words = {
        word
        for name, keywords in rows
        for word in re.findall(r"[a-z]{4,}", f"{name} {keywords or ''}".lower())
    }

    corrected = []
    changed = False
    for word in query.lower().split():
        matches = [] if word in known_words else difflib.get_close_matches(
            word, known_words, n=1, cutoff=0.75
        )
        changed = changed or bool(matches)
        corrected.append(matches[0] if matches else word)
    return " ".join(corrected) if changed else None


# ---------- Logging ----------

def remove_sensitive_text(query):
    """Remove anything that might be personal before a search is saved."""
    return " ".join(SENSITIVE_TEXT.sub(" ", query).split()).lower()


def log_search(filters, results):
    """Save the search for analytics. It's never linked to a visitor.

    A problem saving the log must not stop a citizen from seeing their results.
    """
    safe_query = remove_sensitive_text(filters.query)
    if not safe_query or filters.page != 1:
        return

    top_service = results.items[0]["service"] if results.items else None
    db.session.add(SearchLog(
        query_text=safe_query,
        results_count=results.total,
        top_service_id=top_service.id if top_service else None,
        top_institution_id=top_service.institution_id if top_service else None,
    ))
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Could not save a search log")
