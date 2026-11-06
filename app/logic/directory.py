"""The government institution directory and the office finder.

Your brief's rule applies here too: nothing is assumed to be verified. Every
record carries its own status, and missing details stay empty.
"""

from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import joinedload, selectinload

from app.extensions import db
from app.logic.checklist import OFFICE_TYPE_ORDER
from app.logic.search import clean_query, like_pattern, paginate
from app.logic.verification import STATUS_LABELS, effective_status, overall_status
from app.models import (
    District,
    GovernmentInstitution,
    GovernmentOffice,
    GovernmentService,
    Region,
    ServiceOffice,
)
from app.models.base import INSTITUTION_TYPES

INSTITUTION_TYPE_LABELS = {
    "ministry": "Ministry",
    "department": "Department",
    "agency": "Agency",
    "local_government": "Local government",
    "other": "Other",
}
assert set(INSTITUTION_TYPE_LABELS) == set(INSTITUTION_TYPES)


def record_status(record):
    """The status citizens should see for an institution or office."""
    status = effective_status(record.verification_status, record.review_due_on)
    return {"status": status, "label": STATUS_LABELS[status]}


def open_services(services):
    return [service for service in services if not service.is_archived]


def office_sort_key(office):
    """Local offices come before headquarters."""
    return (OFFICE_TYPE_ORDER[office.office_type], office.name.lower())


# ---------- Institutions ----------

@dataclass
class InstitutionFilters:
    query: str = ""
    institution_type: str = ""
    page: int = 1

    def as_url_values(self):
        values = {"q": self.query, "type": self.institution_type}
        return {name: value for name, value in values.items() if value}


def parse_institution_filters(args):
    chosen_type = args.get("type", "")
    return InstitutionFilters(
        query=clean_query(args.get("q", "")),
        institution_type=chosen_type if chosen_type in INSTITUTION_TYPE_LABELS else "",
        page=max(args.get("page", default=1, type=int) or 1, 1),
    )


def find_institutions(filters):
    statement = (
        select(GovernmentInstitution)
        .where(GovernmentInstitution.is_archived.is_(False))
        .options(
            selectinload(GovernmentInstitution.services),
            selectinload(GovernmentInstitution.offices),
        )
        .order_by(GovernmentInstitution.name)
    )
    for word in filters.query.lower().split():
        pattern = like_pattern(word)
        statement = statement.where(or_(
            GovernmentInstitution.name.ilike(pattern, escape="\\"),
            GovernmentInstitution.acronym.ilike(pattern, escape="\\"),
            GovernmentInstitution.description.ilike(pattern, escape="\\"),
        ))
    if filters.institution_type:
        statement = statement.where(
            GovernmentInstitution.institution_type == filters.institution_type
        )

    items = [
        {
            "institution": institution,
            "type_label": INSTITUTION_TYPE_LABELS[institution.institution_type],
            "service_count": len(open_services(institution.services)),
            "office_count": len([o for o in institution.offices if not o.is_archived]),
            **record_status(institution),
        }
        for institution in db.session.scalars(statement)
    ]
    return paginate(items, filters.page)


def get_institution(slug):
    return db.session.scalar(
        select(GovernmentInstitution)
        .where(GovernmentInstitution.slug == slug, GovernmentInstitution.is_archived.is_(False))
    )


def build_institution_page(institution):
    services = sorted(open_services(institution.services), key=lambda s: s.name.lower())
    offices = sorted(
        (office for office in institution.offices if not office.is_archived),
        key=office_sort_key,
    )
    parent = institution.parent
    return {
        "institution": institution,
        "type_label": INSTITUTION_TYPE_LABELS[institution.institution_type],
        "parent": parent if parent and not parent.is_archived else None,
        "children": sorted(
            (child for child in institution.children if not child.is_archived),
            key=lambda child: child.name.lower(),
        ),
        "services": [
            {"service": service, "status": overall_status(service)} for service in services
        ],
        "offices": [{"office": office, **record_status(office)} for office in offices],
        **record_status(institution),
    }


# ---------- Offices ----------

@dataclass
class OfficeFilters:
    district: int | None = None
    region: int | None = None
    institution: str = ""
    service: str = ""
    page: int = 1

    @property
    def has_filters(self):
        return bool(self.district or self.region or self.institution or self.service)

    def as_url_values(self):
        values = {
            "district": self.district,
            "region": self.region,
            "institution": self.institution,
            "service": self.service,
        }
        return {name: value for name, value in values.items() if value}


def office_filter_options():
    return {
        "districts": db.session.scalars(select(District).order_by(District.name)).all(),
        "regions": db.session.scalars(select(Region).order_by(Region.name)).all(),
        "institutions": db.session.scalars(
            select(GovernmentInstitution)
            .where(GovernmentInstitution.is_archived.is_(False))
            .order_by(GovernmentInstitution.name)
        ).all(),
        "services": db.session.scalars(
            select(GovernmentService)
            .where(GovernmentService.is_archived.is_(False))
            .order_by(GovernmentService.name)
        ).all(),
    }


def parse_office_filters(args, options):
    """Check each value against the real choices, and ignore unknown ones."""

    def known_id(value, records):
        return value if value in {record.id for record in records} else None

    def known_slug(value, records):
        return value if value in {record.slug for record in records} else ""

    return OfficeFilters(
        district=known_id(args.get("district", type=int), options["districts"]),
        region=known_id(args.get("region", type=int), options["regions"]),
        institution=known_slug(args.get("institution", ""), options["institutions"]),
        service=known_slug(args.get("service", ""), options["services"]),
        page=max(args.get("page", default=1, type=int) or 1, 1),
    )


def matching_offices(filters):
    """Open offices that fit the institution and service filters, in any place."""
    statement = (
        select(GovernmentOffice)
        .join(GovernmentOffice.institution)
        .where(GovernmentOffice.is_archived.is_(False))
        .options(
            joinedload(GovernmentOffice.institution),
            joinedload(GovernmentOffice.district).joinedload(District.region),
            selectinload(GovernmentOffice.service_links).joinedload(ServiceOffice.service),
        )
    )
    if filters.institution:
        statement = statement.where(GovernmentInstitution.slug == filters.institution)
    if filters.service:
        statement = statement.where(GovernmentOffice.id.in_(
            select(ServiceOffice.office_id)
            .join(ServiceOffice.service)
            .where(GovernmentService.slug == filters.service)
        ))
    return db.session.scalars(statement).unique().all()


def limit_to_place(offices, filters):
    """Keep offices in the chosen place.

    If a chosen district has none, show the rest of its region and say so,
    because a citizen still needs to know the closest place to go.
    Returns the offices, and the name of the district that had none.
    """
    if filters.district:
        in_district = [office for office in offices if office.district_id == filters.district]
        if in_district:
            return in_district, None

        district = db.session.get(District, filters.district)
        in_region = [
            office for office in offices if office.district.region_id == district.region_id
        ]
        return in_region, district.name

    if filters.region:
        return [o for o in offices if o.district.region_id == filters.region], None

    return offices, None


def describe_office(office):
    services = [
        {
            "service": link.service,
            "status": link.verification_status,
            "label": STATUS_LABELS[link.verification_status],
            "note": link.availability_note,
        }
        for link in office.service_links
        if not link.service.is_archived
    ]
    services.sort(key=lambda entry: entry["service"].name.lower())
    return {"office": office, "services": services, **record_status(office)}


def find_offices(filters):
    """Return one page of offices, and the district that had none, if any."""
    offices, empty_district = limit_to_place(matching_offices(filters), filters)
    items = [describe_office(office) for office in sorted(offices, key=office_sort_key)]
    return paginate(items, filters.page), empty_district
