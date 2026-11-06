"""Stage 6 tests: the homepage, information pages, error pages and seed data."""

import re
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.extensions import db
from app.logic.home import popular_services
from app.models import DailyView, ServiceCategory
from seed.categories import CATEGORIES, seed_categories

ICON_FILE = Path(__file__).resolve().parent.parent / (
    "app/static/vendor/bootstrap-icons/bootstrap-icons.min.css"
)


def page_text(client, address="/"):
    response = client.get(address)
    assert response.status_code == 200
    return response.get_data(as_text=True)


def add_views(service, days_ago=0, count=5):
    db.session.add(DailyView(
        view_date=date.today() - timedelta(days=days_ago),
        service_id=service.id,
        view_count=count,
    ))
    db.session.commit()


# ---------- Homepage content ----------

def test_homepage_explains_its_purpose(client, database):
    text = page_text(client)
    assert "Know Before You Go." in text
    assert "not a government website" in text
    assert "How Citizen Compass works" in text
    assert "How we check information" in text


def test_homepage_shows_all_four_verification_labels(client, database):
    text = page_text(client)
    for label in ["Verified", "Pending verification", "Outdated – review required",
                  "Information unavailable"]:
        assert label in text


def test_empty_database_shows_honest_messages(client, database):
    text = page_text(client)
    assert "No popular services to show yet." in text
    assert "No categories have been added yet." in text
    assert "No institutions have been added yet." in text


def test_contact_email_is_hidden_until_set(client, database):
    assert "mailto:" not in page_text(client)


def test_contact_email_appears_when_set(app, client, database):
    app.config["CONTACT_EMAIL"] = "hello@example.test"
    assert 'href="mailto:hello@example.test"' in page_text(client)


# ---------- No fake buttons ----------

def test_homepage_search_goes_to_the_directory(client, database):
    text = page_text(client)
    assert '<form action="/services"' in text
    assert 'name="q"' in text
    assert ">Services</a>" in text


def test_category_cards_link_to_filtered_results(client, sample):
    assert 'href="/services?category=example-category"' in page_text(client)


def test_unbuilt_features_have_no_links(client, database):
    assert "Report a problem</a>" not in page_text(client)


def test_directories_are_linked_from_the_homepage(client, database):
    text = page_text(client)
    assert 'href="/institutions"' in text
    assert 'href="/offices"' in text
    assert "The office finder isn't available yet." not in text


def test_every_link_on_the_homepage_works(client, database, sample):
    seed_categories()
    text = page_text(client)
    addresses = set(re.findall(r'(?:href|src)="(/[^"#]*)', text))
    assert len(addresses) >= 6

    for address in addresses:
        assert client.get(address).status_code == 200, address


def test_every_page_anchor_exists(client, database):
    text = page_text(client)
    for anchor in re.findall(r'href="(?:/)?#([^"]+)"', text):
        assert f'id="{anchor}"' in text, anchor


# ---------- Data on the homepage ----------

def test_categories_show_their_service_counts(client, sample):
    text = page_text(client)
    assert "Example Category" in text
    assert "1 service" in text


def test_archived_service_is_not_counted(client, sample):
    sample.service.is_archived = True
    db.session.commit()
    assert "No services added yet" in page_text(client)


def test_inactive_category_is_hidden(client, sample):
    sample.category.is_active = False
    db.session.commit()
    assert "Example Category" not in page_text(client)


def test_page_data_is_escaped(client, database):
    db.session.add(ServiceCategory(name="<script>alert(1)</script>", slug="bad"))
    db.session.commit()
    text = page_text(client)
    assert "<script>alert(1)</script>" not in text
    assert "&lt;script&gt;" in text


def test_popular_needs_real_views(client, sample):
    assert popular_services() == []
    assert "No popular services to show yet." in page_text(client)


def test_viewed_service_shows_status_and_demo_label(client, sample):
    add_views(sample.service)
    text = page_text(client)
    assert "No popular services to show yet." not in text
    assert "Example Service" in text
    assert "Demonstration only" in text
    assert 'status-badge status-pending' in text


def test_popular_ignores_old_views(sample):
    add_views(sample.service, days_ago=31)
    assert popular_services() == []


def test_popular_ignores_archived_services(sample):
    add_views(sample.service)
    sample.service.is_archived = True
    db.session.commit()
    assert popular_services() == []


# ---------- Other pages ----------

@pytest.mark.parametrize("address, phrase", [
    ("/disclaimer", "Confirm before you travel"),
    ("/privacy", "We never ask for your National ID number"),
])
def test_information_pages_load(client, database, address, phrase):
    assert phrase in page_text(client, address)


def test_missing_page_uses_the_friendly_template(client):
    response = client.get("/no-such-page")
    assert response.status_code == 404
    assert "Page not found" in response.get_data(as_text=True)


def test_server_error_hides_technical_details(app, client):
    """With no tables created, the homepage query fails."""
    app.config["PROPAGATE_EXCEPTIONS"] = False
    response = client.get("/")
    text = response.get_data(as_text=True)

    assert response.status_code == 500
    assert "Something went wrong" in text
    assert "no such table" not in text
    assert "Traceback" not in text


# ---------- Seed data ----------

def test_seed_adds_all_categories_once(database):
    assert seed_categories() == 14
    assert seed_categories() == 0
    assert db.session.query(ServiceCategory).count() == 14


def test_seed_keeps_an_administrators_edit(database):
    seed_categories()
    category = db.session.query(ServiceCategory).filter_by(slug="health").one()
    category.name = "Edited by an administrator"
    db.session.commit()

    seed_categories()
    assert category.name == "Edited by an administrator"


def test_seed_command_runs(app, database):
    result = app.test_cli_runner().invoke(args=["seed", "categories"])
    assert result.exit_code == 0
    assert "Added 14 categories." in result.output


def test_every_category_icon_exists():
    icons = ICON_FILE.read_text(encoding="utf-8")
    for _, _, icon in CATEGORIES:
        assert f".{icon}::before" in icons, icon
