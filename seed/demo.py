"""Clearly fictional records for testing before real data is added.

Every agency, place, document and service here is invented. Each name says
"Demonstration", and each record is marked is_demo. None of it describes a real
government requirement, and remove_demo_data() deletes all of it.

No fee amounts or processing days are included, even fictional ones, so a
made-up number can never be mistaken for a real one.
"""

from app.extensions import db
from app.logic.verification import create_verification_records
from app.models import (
    District,
    GovernmentInstitution,
    GovernmentOffice,
    GovernmentService,
    OfficialSource,
    ProcessingInformation,
    Region,
    RequiredDocument,
    ServiceCategory,
    ServiceFee,
    ServiceOffice,
    ServiceStep,
    ServiceVariant,
)
from seed.categories import seed_categories

DEMO_REGION = "Demonstration Region"
DEMO_DISTRICTS = ("Demonstration District North", "Demonstration District South")

DEMO_INSTITUTIONS = [
    ("Demonstration Registration Agency", "demonstration-registration-agency", "DEMO-REG"),
    ("Demonstration Licensing Office", "demonstration-licensing-office", "DEMO-LIC"),
]

# example.org is reserved for examples, so this can never be a real agency's page.
DEMO_SOURCE_URL = "https://example.org/citizen-compass-demonstration"

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


def add_checklist_details(service, source):
    """Fill one fictional service, so every part of the checklist can be tested."""
    service.description = "This fictional description shows where the real explanation will appear."
    service.eligibility = "Fictional example: anyone testing Citizen Compass."

    damaged = ServiceVariant(name="Demonstration: damaged card", is_default=True, display_order=1)
    lost = ServiceVariant(name="Demonstration: lost card", display_order=2)
    service.variants.extend([damaged, lost])

    service.steps.extend([
        ServiceStep(step_number=1, title="Demonstration step: gather your papers",
                    instructions="A fictional step shown before the visit.", source=source),
        ServiceStep(step_number=2, stage="at_office", title="Demonstration step: visit the desk",
                    instructions="A fictional step shown at the office.", source=source),
    ])

    service.documents.extend([
        RequiredDocument(
            name="Demonstration application form", source=source, display_order=1,
            original_required=True, photocopies=1, certified_copy_accepted=False,
            instructions="A fictional instruction. Shown for every situation.",
        ),
        RequiredDocument(
            name="Demonstration damaged card", variant=damaged, source=source, display_order=2,
            original_required=True,
        ),
        RequiredDocument(
            name="Demonstration loss letter", variant=lost, source=source, display_order=3,
            original_required=True, max_age_days=30,
            instructions="A fictional document that must be recent.",
        ),
        RequiredDocument(
            name="Demonstration supporting letter", is_mandatory=False, source=source,
            display_order=4,
        ),
    ])

    service.fees.extend([
        ServiceFee(fee_name="Demonstration ordinary fee", service_speed="ordinary", source=source),
        ServiceFee(fee_name="Demonstration express fee", service_speed="express",
                   is_mandatory=False, source=source),
    ])

    service.processing.append(ProcessingInformation(
        service_speed="ordinary",
        duration_note="A fictional note. No real processing time is shown.",
        delay_factors="Fictional example: missing papers.",
        source=source,
    ))

    for record in service.verification_records:
        record.source = source


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

    source = OfficialSource(
        institution=institutions[first_slug],
        title="Demonstration source (not a real official page)",
        url=DEMO_SOURCE_URL,
    )
    db.session.add(source)

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

        if slug == DEMO_SERVICES[0][1]:
            add_checklist_details(service, source)

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

    source = db.session.scalar(db.select(OfficialSource).filter_by(url=DEMO_SOURCE_URL))
    if source:
        db.session.delete(source)
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
