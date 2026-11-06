"""The standard service categories.

These are our own way of grouping services, not government facts, so they need
no official source. Administrators can add more later.
"""

from app.extensions import db
from app.models import ServiceCategory

# Name, web address part, Bootstrap icon.
CATEGORIES = [
    ("National identification and civil registration", "national-id-civil-registration", "bi-person-vcard"),
    ("Immigration and passports", "immigration-passports", "bi-passport"),
    ("Taxation and financial services", "taxation-financial", "bi-cash-coin"),
    ("Business registration and licensing", "business-registration", "bi-shop"),
    ("Land and property services", "land-property", "bi-map"),
    ("Education services", "education", "bi-mortarboard"),
    ("Health services", "health", "bi-heart-pulse"),
    ("Agriculture services", "agriculture", "bi-flower1"),
    ("Transport and driving services", "transport-driving", "bi-car-front"),
    ("Legal and judicial services", "legal-judicial", "bi-bank"),
    ("Local government services", "local-government", "bi-building"),
    ("Social development services", "social-development", "bi-people"),
    ("Employment and labour services", "employment-labour", "bi-briefcase"),
    ("Utilities and infrastructure", "utilities-infrastructure", "bi-lightning-charge"),
]


def seed_categories():
    """Add any missing categories and return how many were added.

    Existing categories are left alone, so an administrator's edits are kept.
    """
    existing = set(db.session.scalars(db.select(ServiceCategory.slug)))
    added = 0
    for position, (name, slug, icon) in enumerate(CATEGORIES, start=1):
        if slug not in existing:
            db.session.add(
                ServiceCategory(name=name, slug=slug, icon=icon, display_order=position)
            )
            added += 1
    db.session.commit()
    return added
