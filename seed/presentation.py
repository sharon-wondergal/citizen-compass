"""A fuller set of fictional records, so the prototype can be presented.

Like seed/demo.py, everything here is invented. Each name says "Demonstration",
each record is marked is_demo, and "flask seed remove-demo" deletes all of it.
There are no fee amounts or processing days, even fictional ones.

The view counts are also invented. They exist so the Popular services section
has something to show during a presentation, and they're deleted with the services.
"""

from datetime import date

from app.extensions import db
from app.logic.verification import create_verification_records
from app.models import (
    DailyView,
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
)
from seed.demo import DEMO_SOURCE_URL, seed_demo_data

SECOND_REGION = "Demonstration Region Two"
EXTRA_DISTRICTS = ("Demonstration District East", "Demonstration District West")

# Name, web address part, acronym, type.
EXTRA_INSTITUTIONS = [
    ("Demonstration Ministry of Services", "demonstration-ministry-of-services", "DEMO-MIN", "ministry"),
    ("Demonstration Revenue Office", "demonstration-revenue-office", "DEMO-REV", "agency"),
    ("Demonstration Transport Office", "demonstration-transport-office", "DEMO-TRA", "agency"),
    ("Demonstration Lands Office", "demonstration-lands-office", "DEMO-LAN", "department"),
    ("Demonstration Education Board", "demonstration-education-board", "DEMO-EDU", "agency"),
]

# Name, category, institution, mode, keywords, summary.
EXTRA_SERVICES = [
    ("Demonstration Birth Record Request", "national-id-civil-registration",
     "demonstration-registration-agency", "physical", "example birth certificate child",
     "A fictional example of requesting a birth record."),
    ("Demonstration Tax Number Registration", "taxation-financial",
     "demonstration-revenue-office", "online", "example tin tax number",
     "A fictional example of registering for a tax number."),
    ("Demonstration Trading Licence", "business-registration",
     "demonstration-licensing-office", "hybrid", "example shop trading licence",
     "A fictional example of applying for a trading licence."),
    ("Demonstration Land Record Search", "land-property",
     "demonstration-lands-office", "physical", "example land title search",
     "A fictional example of searching a land record."),
    ("Demonstration Exam Certificate Check", "education",
     "demonstration-education-board", "hybrid", "example results certificate school",
     "A fictional example of checking an academic certificate."),
    ("Demonstration Driving Permit Renewal", "transport-driving",
     "demonstration-transport-office", "physical", "example driving licence permit renew",
     "A fictional example of renewing a driving permit."),
    ("Demonstration Clinic Registration", "health",
     "demonstration-ministry-of-services", "physical", "example health clinic hospital",
     "A fictional example of registering a health facility."),
    ("Demonstration Farm Input Permit", "agriculture",
     "demonstration-ministry-of-services", "online", "example farm seed permit",
     "A fictional example of applying for a farming permit."),
    ("Demonstration Clearance Letter", "legal-judicial",
     "demonstration-ministry-of-services", "physical", "example police clearance good conduct",
     "A fictional example of requesting a clearance letter."),
    ("Demonstration Building Plan Approval", "local-government",
     "demonstration-ministry-of-services", "physical", "example building plan council",
     "A fictional example of getting a building plan approved."),
    ("Demonstration Community Group Registration", "social-development",
     "demonstration-ministry-of-services", "physical", "example community group youth women",
     "A fictional example of registering a community group."),
    ("Demonstration Work Permit Check", "employment-labour",
     "demonstration-ministry-of-services", "hybrid", "example job work labour",
     "A fictional example of checking a work permit."),
    ("Demonstration Water Connection Request", "utilities-infrastructure",
     "demonstration-ministry-of-services", "hybrid", "example water connection utility",
     "A fictional example of requesting a water connection."),
]

# Fictional view totals, highest first, so Popular services has an order.
VIEW_COUNTS = (48, 41, 36, 29, 23, 18)


def add_simple_details(service, source):
    """Give a fictional service enough detail to fill its checklist."""
    service.description = "This fictional description shows where the real explanation will appear."
    service.eligibility = "Fictional example: anyone testing Citizen Compass."
    service.steps.extend([
        ServiceStep(step_number=1, title="Demonstration step: prepare your papers",
                    instructions="A fictional step shown before the visit.", source=source),
        ServiceStep(step_number=2, stage="at_office", title="Demonstration step: hand them in",
                    instructions="A fictional step shown at the office.", source=source),
    ])
    service.documents.extend([
        RequiredDocument(name="Demonstration application form", source=source, display_order=1,
                         original_required=True, photocopies=1, certified_copy_accepted=False),
        RequiredDocument(name="Demonstration proof of identity", source=source, display_order=2,
                         original_required=True, photocopies=1,
                         instructions="A fictional instruction."),
        RequiredDocument(name="Demonstration supporting letter", is_mandatory=False,
                         source=source, display_order=3),
    ])
    service.fees.append(
        ServiceFee(fee_name="Demonstration service fee", service_speed="ordinary", source=source)
    )
    service.processing.append(ProcessingInformation(
        service_speed="ordinary",
        duration_note="A fictional note. No real processing time is shown.",
        source=source,
    ))
    for record in service.verification_records:
        record.source = source


def seed_presentation_data():
    """Add the fuller fictional set and return how many services were added."""
    seed_demo_data()

    first_slug = EXTRA_INSTITUTIONS[0][1]
    if db.session.scalar(db.select(GovernmentInstitution).filter_by(slug=first_slug)):
        return 0

    source = db.session.scalar(db.select(OfficialSource).filter_by(url=DEMO_SOURCE_URL))
    categories = {
        category.slug: category for category in db.session.scalars(db.select(ServiceCategory))
    }

    region = Region(name=SECOND_REGION)
    districts = [District(name=name, region=region) for name in EXTRA_DISTRICTS]
    db.session.add(region)

    for name, slug, acronym, kind in EXTRA_INSTITUTIONS:
        db.session.add(GovernmentInstitution(
            name=name, slug=slug, acronym=acronym, institution_type=kind,
            description="A fictional institution for testing Citizen Compass. It doesn't exist.",
            is_demo=True,
        ))
    db.session.flush()

    institutions = {
        institution.slug: institution
        for institution in db.session.scalars(
            db.select(GovernmentInstitution).filter_by(is_demo=True)
        )
    }
    for slug in (item[1] for item in EXTRA_INSTITUTIONS[1:]):
        institutions[slug].parent = institutions[first_slug]

    # Every institution gets an office in each new district, so the office
    # finder and the "nearest first" sorting have something to show.
    offices = {}
    for slug, institution in institutions.items():
        offices[slug] = [
            GovernmentOffice(
                institution=institution,
                district=district,
                name=f"{institution.name} {district.name.removeprefix('Demonstration District ')} Office",
                is_demo=True,
            )
            for district in districts
        ]
        db.session.add_all(offices[slug])

    for name, category, institution, mode, keywords, summary in EXTRA_SERVICES:
        service = GovernmentService(
            name=name,
            slug=name.lower().replace(" ", "-"),
            category=categories[category],
            institution=institutions[institution],
            summary=summary,
            delivery_mode=mode,
            keywords=keywords,
            is_demo=True,
        )
        create_verification_records(service)
        add_simple_details(service, source)
        for office in offices[institution]:
            service.office_links.append(ServiceOffice(office=office))
        db.session.add(service)

    # The two simpler services from seed/demo.py get details too.
    db.session.flush()
    services = db.session.scalars(
        db.select(GovernmentService).filter_by(is_demo=True).order_by(GovernmentService.id)
    ).all()
    for service in services:
        if not service.documents:
            add_simple_details(service, source)

    for service, count in zip(services, VIEW_COUNTS):
        db.session.add(DailyView(view_date=date.today(), service_id=service.id, view_count=count))

    db.session.commit()
    return len(EXTRA_SERVICES)
