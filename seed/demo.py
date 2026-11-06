"""Clearly fictional records for testing search before real data is added.

Every agency, place and service here is invented. Each name says
"Demonstration", and each record is marked is_demo. None of it describes a real
government requirement, and remove_demo_data() deletes all of it.
"""

from app.extensions import db
from app.logic.verification import create_verification_records
from app.models import (
    District,
    GovernmentInstitution,
    GovernmentOffice,
    GovernmentService,
    Region,
    ServiceCategory,
    ServiceOffice,
)
from seed.categories import seed_categories

DEMO_REGION = "Demonstration Region"
DEMO_DISTRICTS = ("Demonstration District North", "Demonstration District South")

DEMO_INSTITUTIONS = [
    ("Demonstration Registration Agency", "demonstration-registration-agency", "DEMO-REG"),
    ("Demonstration Licensing Office", "demonstration-licensing-office", "DEMO-LIC"),
]

# Name, web address part, category, institution, mode, keywords, districts.
DEMO_SERVICES = [
    (
        "Demonstration Identity Card Replacement",
        "demonstration-identity-card-replacement",
        "national-id-civil-registration",
        "demonstration-registration-agency",
        "physical",
        "example id card lost damaged",
        DEMO_DISTRICTS,
    ),
    (
        "Demonstration Travel Document Renewal",
        "demonstration-travel-document-renewal",
        "immigration-passports",
        "demonstration-registration-agency",
        "hybrid",
        "example travel renew",
        DEMO_DISTRICTS[:1],
    ),
    (
        "Demonstration Business Name Filing",
        "demonstration-business-name-filing",
        "business-registration",
        "demonstration-licensing-office",
        "online",
        "example company shop trading",
        (),
    ),
]


def seed_demo_data():
    """Add the demonstration records and return how many services were added."""
    first_slug = DEMO_INSTITUTIONS[0][1]
    already_added = db.session.scalar(
        db.select(GovernmentInstitution).filter_by(slug=first_slug)
    )
    if already_added:
        return 0

    seed_categories()
    categories = {
        category.slug: category for category in db.session.scalars(db.select(ServiceCategory))
    }

    region = Region(name=DEMO_REGION)
    districts = {name: District(name=name, region=region) for name in DEMO_DISTRICTS}
    db.session.add(region)

    institutions = {}
    for name, slug, acronym in DEMO_INSTITUTIONS:
        institutions[slug] = GovernmentInstitution(
            name=name, slug=slug, acronym=acronym, is_demo=True
        )
    db.session.add_all(institutions.values())

    offices = {}
    for district_name, district in districts.items():
        offices[district_name] = GovernmentOffice(
            institution=institutions[first_slug],
            district=district,
            name=f"{district_name} Office",
            is_demo=True,
        )
    db.session.add_all(offices.values())

    for name, slug, category, institution, mode, keywords, office_districts in DEMO_SERVICES:
        service = GovernmentService(
            name=name,
            slug=slug,
            category=categories[category],
            institution=institutions[institution],
            summary="A fictional service for testing Citizen Compass. Not a real requirement.",
            delivery_mode=mode,
            keywords=keywords,
            is_demo=True,
        )
        create_verification_records(service)
        for district_name in office_districts:
            service.office_links.append(ServiceOffice(office=offices[district_name]))
        db.session.add(service)

    db.session.commit()
    return len(DEMO_SERVICES)


def remove_demo_data():
    """Delete every demonstration record and return how many services were removed."""
    services = db.session.scalars(db.select(GovernmentService).filter_by(is_demo=True)).all()
    removed = len(services)
    for service in services:
        db.session.delete(service)
    db.session.flush()

    for office in db.session.scalars(db.select(GovernmentOffice).filter_by(is_demo=True)):
        db.session.delete(office)
    db.session.flush()

    for institution in db.session.scalars(
        db.select(GovernmentInstitution).filter_by(is_demo=True)
    ):
        db.session.delete(institution)

    for district in db.session.scalars(
        db.select(District).where(District.name.in_(DEMO_DISTRICTS))
    ):
        db.session.delete(district)
    db.session.flush()

    region = db.session.scalar(db.select(Region).filter_by(name=DEMO_REGION))
    if region:
        db.session.delete(region)

    db.session.commit()
    return removed
