"""Real government services, entered from official pages read on 7 November 2026.

Rules followed here:

* Only what an official page states is entered. Everything else stays blank, so
  citizens see "Not confirmed".
* Where official information disagrees or couldn't be read, the value stays
  blank, and the record's notes say why.
* Nothing is verified. Each section is pending until a second person checks it
  against the source, and fee amounts stay hidden from citizens until then.

Sections need checking again before any public use, because agencies change
their requirements.
"""

from datetime import date

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

ENTRY_NOTE = "Entered from the official source on 7 November 2026. Awaiting a second person's check."

INSTITUTIONS = {
    "dcic": {
        "name": "Directorate of Citizenship and Immigration Control",
        "slug": "directorate-of-citizenship-and-immigration-control",
        "acronym": "DCIC",
        "institution_type": "department",
        "website": "https://immigration.go.ug/",
        "source_url": "https://immigration.go.ug/node/119",
    },
    "nira": {
        "name": "National Identification and Registration Authority",
        "slug": "national-identification-and-registration-authority",
        "acronym": "NIRA",
        "institution_type": "agency",
        "website": "https://www.nira.go.ug/",
        "source_url": "https://servicebooking.nira.go.ug/service/replacement-national-id",
    },
    "ura": {
        "name": "Uganda Revenue Authority",
        "slug": "uganda-revenue-authority",
        "acronym": "URA",
        "institution_type": "agency",
        "website": "https://ura.go.ug/",
        "phone": "0800 117 000 / 0800 217 000",
        "source_url": "https://ura.go.ug/en/domestic-taxes/tin-application/tin-registration-individual/",
    },
    "ursb": {
        "name": "Uganda Registration Services Bureau",
        "slug": "uganda-registration-services-bureau",
        "acronym": "URSB",
        "institution_type": "agency",
        "website": "https://ursb.go.ug/",
        "phone": "+256 200 404 700",
        "email": "ursb@ursb.go.ug",
        "headquarters": "Uganda Business Facilitation Centre, Plot 1 Baskerville Avenue, Kololo, Kampala",
        "source_url": "https://ursb.go.ug/services/business-registration/",
    },
    "upf": {
        "name": "Uganda Police Force",
        "slug": "uganda-police-force",
        "acronym": "UPF",
        "institution_type": "agency",
        "website": "https://upf.go.ug/",
        "source_url": "https://upf.go.ug/certificate-of-good-conduct-application-made-easy/",
    },
    "nche": {
        "name": "National Council for Higher Education",
        "slug": "national-council-for-higher-education",
        "acronym": "NCHE",
        "institution_type": "agency",
        "website": "https://unche.or.ug/",
        "source_url": "https://unche.or.ug/recognition-and-equation/",
    },
}

# Key: (institution, title, web address, type, published date if the page has one).
SOURCES = {
    "passport": ("dcic", "Ordinary Passport", "https://immigration.go.ug/node/119", "web_page", None),
    "nira_replacement": (
        "nira", "Replacement of National ID",
        "https://servicebooking.nira.go.ug/service/replacement-national-id", "web_page", None,
    ),
    "tin": (
        "ura", "TIN Registration - Individual",
        "https://ura.go.ug/en/domestic-taxes/tin-application/tin-registration-individual/",
        "web_page", None,
    ),
    "ursb_fees": (
        "ursb", "Business, Company and Document registration fees",
        "https://ursb.go.ug/business-company-and-document-registration-fees/", "web_page", None,
    ),
    "ursb_registration": (
        "ursb", "Business Registration", "https://ursb.go.ug/services/business-registration/",
        "web_page", None,
    ),
    "good_conduct_2024": (
        "upf", "Certificate of Good Conduct Application Made Easy",
        "https://upf.go.ug/certificate-of-good-conduct-application-made-easy/", "web_page",
        date(2024, 11, 13),
    ),
    "good_conduct_2018": (
        "upf", "What You Need To Know to Acquire Certificate of Good Conduct",
        "https://upf.go.ug/what-you-need-to-know-to-acquire-certificate-of-good-conduct/",
        "web_page", date(2018, 10, 22),
    ),
    "nche": (
        "nche", "Recognition and Equation",
        "https://unche.or.ug/recognition-and-equation/", "web_page", None,
    ),
}

OFFICES = {
    "ursb_kololo": {
        "institution": "ursb",
        "name": "URSB Uganda Business Facilitation Centre",
        "office_type": "headquarters",
        "physical_address": "Plot 1 Baskerville Avenue, Kololo, Kampala",
        "phone": "+256 200 404 700",
        "email": "helpdesk@ursb.go.ug",
        "source": "ursb_registration",
    },
    "interpol_kololo": {
        "institution": "upf",
        "name": "Interpol Office Kololo",
        "office_type": "other",
        "physical_address": "Plot 12, Mabua Road, Kololo",
        "email": "Interpol@upf.go.ug",
        "source": "good_conduct_2024",
    },
}

SERVICES = [
    {
        "name": "Ordinary Passport Application",
        "slug": "ordinary-passport-application",
        "institution": "dcic",
        "category": "immigration-passports",
        "summary": "Apply for an ordinary Ugandan passport online, then attend enrolment at your chosen passport centre.",
        "description": "A passport serves as a travel document issued to Ugandan citizens for travelling abroad.",
        "delivery_mode": "hybrid",
        "online_url": "https://passports.go.ug/",
        "keywords": "passport travel document immigration internal affairs abroad express",
        "source": "passport",
        "variants": ["Adult", "Minor"],
        "documents": [
            ("National ID or National Identification Number", "Adult", True, None),
            ("Recommendation letter with the recommender's National ID", "Adult", True, None),
            ("Documents supporting your profession", "Adult", False, "If applicable."),
            ("Birth certificate", "Minor", True, None),
            ("Parents' National IDs", "Minor", True, None),
            ("Parents' passports", "Minor", True, None),
            ("Parental consent letter", "Minor", True, None),
            ("Adoption order from the High Court of Uganda", "Minor", False, "If the child is adopted."),
        ],
        "fees": [
            {"fee_name": "Ordinary passport", "service_speed": "ordinary", "amount_ugx": 250000},
            {"fee_name": "Express processing fee (extra)", "service_speed": "express",
             "amount_ugx": 150000, "is_mandatory": False,
             "payment_instructions": "Paid separately in a bank."},
        ],
        "steps": [
            ("before_visit", "Open the passport portal", "Go to the DCIC Passport Portal.", "https://passports.go.ug/"),
            ("before_visit", "Complete the application form", "Accept the terms, answer the security questions and fill in the form.", None),
            ("before_visit", "Pay the fee", "Print the payment advice form, then pay at the bank and by the method you selected.", None),
            ("before_visit", "Book an appointment", "Use the link on the portal's home page, then print the appointment form.", None),
            ("at_office", "Attend enrolment", "Go to your chosen passport centre with the appointment form and required documents.", None),
        ],
        "notes": {
            "processing": "The source doesn't state a processing time.",
            "offices": "The source doesn't list passport centres.",
            "documents": "The source gives no separate lists for renewal or a lost passport.",
        },
    },
    {
        "name": "Replacement of National ID",
        "slug": "replacement-of-national-id",
        "institution": "nira",
        "category": "national-id-civil-registration",
        "summary": "Replace a National ID. The official page lists a police letter and a payment receipt.",
        "online_url": "https://servicebooking.nira.go.ug/service/replacement-national-id",
        "keywords": "national id ndaga muntu nira lost damaged replace card nin",
        "source": "nira_replacement",
        "documents": [
            ("A letter from Police", None, True, None),
            ("Payment receipt", None, True, None),
        ],
        "fees": [{"fee_name": "Replacement fee", "amount_ugx": None}],
        "steps": [
            ("before_visit", "Pay at a bank", "Visit a nearby bank and say you want to pay for the NIRA National ID replacement.", None),
            ("at_office", "Bring your receipt", "Come with your payment receipt.", None),
        ],
        "notes": {
            "fees": "The booking page says shs. 50,000, but doesn't separate lost and damaged cards. "
                    "Other reports give a higher fee for damaged cards, and NIRA's fee page couldn't "
                    "be opened. Left blank until confirmed.",
            "processing": "The source doesn't state a processing time.",
            "offices": "The source doesn't say where to submit the request.",
        },
    },
    {
        "name": "Individual TIN Application",
        "slug": "individual-tin-application",
        "institution": "ura",
        "category": "taxation-financial",
        "summary": "Apply for a Tax Identification Number as an individual.",
        "description": "Any person likely to transact in any tax related business with URA is required to apply for a TIN.",
        "eligibility": "Any person who is likely to transact in any tax related business with URA.",
        "online_url": "https://ura.go.ug/en/domestic-taxes/tin-application/tin-registration-individual/",
        "keywords": "tin tax identification number ura revenue register",
        "source": "tin",
        "variants": ["Ugandan citizen (18 or over)", "Minor", "Non-citizen"],
        "documents": [
            ("National ID", "Ugandan citizen (18 or over)", True, None),
            ("Copy of the legal or court document of guardianship", "Minor", True, None),
            ("Passport", "Non-citizen", True, None),
            ("Visa or work permit", "Non-citizen", False, "Where applicable."),
            ("Refugee ID", "Non-citizen", False, "For refugees."),
            ("Copies of signed registration forms with copies of identification documents", None, True,
             "Required before a TIN is issued."),
        ],
        "steps": [
            ("before_visit", "Apply online", "Complete and upload the Excel template through the online application.",
             "https://ura.go.ug/en/domestic-taxes/tin-application/tin-registration-individual/"),
            ("after_visit", "Wait for approval", "A URA staff member verifies and approves the application.", None),
        ],
        "notes": {
            "fees": "The source doesn't state a fee, so none is entered.",
            "processing": "The source doesn't state a processing time.",
            "offices": "The source mentions URA offices and One-stop stations without listing them.",
        },
    },
    {
        "name": "Business Name Registration",
        "slug": "business-name-registration",
        "institution": "ursb",
        "category": "business-registration",
        "summary": "Reserve and register a business name with URSB.",
        "online_url": "https://eregistry.ursb.go.ug/",
        "keywords": "business name register shop trading ursb sole proprietor",
        "source": "ursb_fees",
        "fees": [
            {"fee_name": "Reservation of a business name", "amount_ugx": 35000},
            {"fee_name": "Registration of a business name", "amount_ugx": 55000},
        ],
        "offices": ["ursb_kololo"],
        "notes": {
            "documents": "URSB's service pages couldn't be opened, so no documents are entered.",
            "processing": "The source doesn't state a processing time.",
            "fees": "The source states no effective date or payment instructions.",
        },
    },
    {
        "name": "Company Registration",
        "slug": "company-registration",
        "institution": "ursb",
        "category": "business-registration",
        "summary": "Register a company with URSB. The fee depends on the company's nominal share capital.",
        "online_url": "https://eregistry.ursb.go.ug/",
        "keywords": "company incorporate limited register ursb share capital",
        "source": "ursb_fees",
        "fees": [
            {"fee_name": "Company with nominal share capital up to UGX 5,000,000", "amount_ugx": 105000},
            {"fee_name": "Company with nominal share capital above UGX 5,000,000", "amount_ugx": None},
        ],
        "offices": ["ursb_kololo"],
        "notes": {
            "fees": "For share capital above UGX 5,000,000, the source says 1.5% of nominal share "
                    "capital, so no single amount can be entered.",
            "documents": "URSB's service pages couldn't be opened, so no documents are entered.",
            "processing": "The source doesn't state a processing time.",
        },
    },
    {
        "name": "Certificate of Good Conduct",
        "slug": "certificate-of-good-conduct",
        "institution": "upf",
        "category": "legal-judicial",
        "summary": "Apply for a police certificate of good conduct. It's valid for six months from the date of issue.",
        "description": "The certificate is valid for six months from the date of issuance.",
        "delivery_mode": "hybrid",
        "online_url": "https://www.upf.go.ug/services",
        "keywords": "police clearance good conduct interpol certificate employment abroad",
        "source": "good_conduct_2024",
        "document_source": "good_conduct_2018",
        "documents": [
            ("A valid identity document", None, True,
             "A driving permit, passport, national identity card or refugee card."),
            ("Two passport-size photos", None, True, None),
            ("Formal application letter", None, True,
             "Addressed to the Director of INTERPOL and International Relations."),
        ],
        "fees": [
            {"fee_name": "Certificate of Good Conduct", "amount_ugx": 76000},
            {"fee_name": "Bank charges", "fee_kind": "other_charge", "amount_ugx": 2300,
             "is_mandatory": False},
            {"fee_name": "Charges if paying by MTN Mobile Money", "fee_kind": "other_charge",
             "amount_ugx": 3700, "is_mandatory": False},
        ],
        "steps": [
            ("before_visit", "Register and apply", "Register on the Uganda Police website and complete the application form.",
             "https://www.upf.go.ug/services"),
            ("before_visit", "Pay the fees", "Pay the official fee and charges.", None),
            ("before_visit", "Book an appointment", "Book a fingerprint capture appointment.", None),
            ("at_office", "Give your fingerprints", "Attend your fingerprint capture appointment.", None),
        ],
        "processing": {
            "min_working_days": 5,
            "max_working_days": 5,
            "basis": "official_standard",
            "duration_note": "The source says processing was reduced from 7 to 5 working days.",
        },
        "offices": ["interpol_kololo"],
        "notes": {
            "documents": "This list comes from a police page dated 22 October 2018. Check it's still current.",
            "processing": "The source doesn't say when the time starts.",
        },
    },
    {
        "name": "Recognition and Equation of Qualifications",
        "slug": "recognition-and-equation-of-qualifications",
        "institution": "nche",
        "category": "education",
        "summary": "Apply to have your qualifications recognised or equated.",
        "online_url": "https://reqims.unche.or.ug/application/index",
        "keywords": "nche equate equation qualifications degree diploma foreign academic verification",
        "source": "nche",
        "variants": ["Foreign qualifications", "Local qualifications"],
        "documents": [
            ("A duly filled-in application form", None, True, None),
            ("Certified photocopies of all certificates and transcripts", None, True, None),
            ("A copy of the National Identity Card or Passport", None, True, None),
            ("A paid URA Payment Reference Number", None, True, None),
            ("Statutory declaration or deed poll, and a copy of the newspaper where the change was published",
             None, False, "If names vary across certificates."),
            ("Translated copies", "Foreign qualifications", False, "If qualifications are not in English."),
        ],
        "fees": [{"fee_name": "Application fee", "amount_ugx": None}],
        "processing": {
            "basis": "official_standard",
            "duration_note": "Processed within three (3) months.",
        },
        "notes": {
            "fees": "The source requires a paid URA Payment Reference Number but states no amount.",
            "offices": "The source doesn't include an office address.",
        },
    },
]


def get_or_create_place():
    region = db.session.scalar(db.select(Region).filter_by(name="Central"))
    if region is None:
        region = Region(name="Central")
        db.session.add(region)
    district = db.session.scalar(db.select(District).filter_by(name="Kampala"))
    if district is None:
        district = District(name="Kampala", region=region)
        db.session.add(district)
    return district


def get_or_create_institutions():
    institutions = {}
    for key, values in INSTITUTIONS.items():
        institution = db.session.scalar(
            db.select(GovernmentInstitution).filter_by(slug=values["slug"])
        )
        if institution is None:
            institution = GovernmentInstitution(**values)
            db.session.add(institution)
        institutions[key] = institution
    return institutions


def get_or_create_sources(institutions):
    sources = {}
    for key, (institution, title, url, source_type, published_on) in SOURCES.items():
        source = db.session.scalar(db.select(OfficialSource).filter_by(url=url))
        if source is None:
            source = OfficialSource(
                institution=institutions[institution], title=title, url=url,
                source_type=source_type, published_on=published_on,
            )
            db.session.add(source)
        sources[key] = source
    return sources


def get_or_create_offices(institutions, sources, district):
    offices = {}
    for key, values in OFFICES.items():
        details = dict(values)
        institution = institutions[details.pop("institution")]
        source = sources[details.pop("source")]
        office = db.session.scalar(
            db.select(GovernmentOffice).filter_by(name=details["name"])
        )
        if office is None:
            office = GovernmentOffice(
                institution=institution, district=district, source=source, **details
            )
            db.session.add(office)
        offices[key] = (office, source)
    return offices


def add_service(details, categories, institutions, sources, offices):
    source = sources[details["source"]]
    document_source = sources[details.get("document_source", details["source"])]

    service = GovernmentService(
        name=details["name"],
        slug=details["slug"],
        institution=institutions[details["institution"]],
        category=categories[details["category"]],
        summary=details["summary"],
        description=details.get("description"),
        eligibility=details.get("eligibility"),
        delivery_mode=details.get("delivery_mode"),
        online_url=details.get("online_url"),
        keywords=details["keywords"],
    )

    variants = {}
    for position, name in enumerate(details.get("variants", []), start=1):
        variants[name] = ServiceVariant(name=name, is_default=position == 1, display_order=position)
        service.variants.append(variants[name])

    documents = details.get("documents", [])
    for position, (name, variant, required, instructions) in enumerate(documents, start=1):
        service.documents.append(RequiredDocument(
            name=name, variant=variants.get(variant), is_mandatory=required,
            instructions=instructions, source=document_source, display_order=position,
        ))

    for position, fee in enumerate(details.get("fees", []), start=1):
        service.fees.append(ServiceFee(source=source, display_order=position, **fee))

    steps = details.get("steps", [])
    for number, (stage, title, instructions, link) in enumerate(steps, start=1):
        service.steps.append(ServiceStep(
            step_number=number, stage=stage, title=title, instructions=instructions,
            action_url=link, source=source,
        ))

    if "processing" in details:
        service.processing.append(ProcessingInformation(source=source, **details["processing"]))

    for key in details.get("offices", []):
        office, office_source = offices[key]
        service.office_links.append(ServiceOffice(office=office, source=office_source))

    create_verification_records(service)
    notes = details.get("notes", {})
    for record in service.verification_records:
        record.source = document_source if record.section == "documents" else source
        record.notes = " ".join(filter(None, [ENTRY_NOTE, notes.get(record.section)]))

    db.session.add(service)


def seed_real_services():
    """Add any real services not already present and return how many were added."""
    existing = set(db.session.scalars(db.select(GovernmentService.slug)))
    missing = [details for details in SERVICES if details["slug"] not in existing]
    if not missing:
        return 0

    seed_categories()
    categories = {
        category.slug: category for category in db.session.scalars(db.select(ServiceCategory))
    }
    district = get_or_create_place()
    institutions = get_or_create_institutions()
    sources = get_or_create_sources(institutions)
    offices = get_or_create_offices(institutions, sources, district)
    db.session.flush()

    for details in missing:
        add_service(details, categories, institutions, sources, offices)

    db.session.commit()
    return len(missing)
