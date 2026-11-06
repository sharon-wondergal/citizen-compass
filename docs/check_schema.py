"""Stage 2 design check for Citizen Compass.

Builds docs/schema_prototype.sql in a temporary in-memory SQLite database,
then tries good and bad data to prove the design's rules work.

Run it from the project folder:

    python docs/check_schema.py

It needs no packages and creates no files. All sample data is invented
("Example Agency") and only exists while the script runs.
"""

import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

SCHEMA_FILE = Path(__file__).with_name("schema_prototype.sql")
EXPECTED_TABLES = 19

# Worst first. The overall status of a service is its weakest section.
STATUS_RANK = ["unavailable", "outdated", "pending", "verified"]

results = []


def report(passed, description):
    results.append(passed)
    print(f"[{'PASS' if passed else 'FAIL'}] {description}")


def accepted(db, description, sql, params=()):
    """This statement should work."""
    try:
        db.execute(sql, params)
        report(True, description)
    except sqlite3.IntegrityError as error:
        report(False, f"{description} (wrongly rejected: {error})")


def rejected(db, description, sql, params=()):
    """The database should refuse this statement."""
    try:
        db.execute(sql, params)
        report(False, f"{description} (wrongly accepted)")
    except sqlite3.IntegrityError as error:
        # Show which rule fired, so a test cannot pass for the wrong reason.
        report(True, f"{description}\n       refused by: {error}")


def effective_status(stored_status, review_due_on, today):
    """A verified record past its review date is shown as outdated."""
    if stored_status == "verified" and review_due_on and review_due_on < today:
        return "outdated"
    return stored_status


def overall_status(section_statuses):
    """Return the weakest status, so a service never looks too certain."""
    return min(section_statuses, key=STATUS_RANK.index)


def add_sample_data(db):
    db.executescript(
        """
        INSERT INTO regions (id, name) VALUES (1, 'Example Region');
        INSERT INTO districts (id, name, region_id) VALUES (1, 'Example District', 1);
        INSERT INTO admin_users (id, full_name, email, password_hash, role) VALUES
            (1, 'Example Editor', 'editor@example.test', 'x', 'editor'),
            (2, 'Example Verifier', 'verifier@example.test', 'x', 'verifier');
        INSERT INTO government_institutions (id, name, slug, is_demo)
            VALUES (1, 'Example Agency', 'example-agency', 1);
        INSERT INTO official_sources (id, institution_id, title, url)
            VALUES (1, 1, 'Example Source', 'https://example.test/source');
        INSERT INTO service_categories (id, name, slug)
            VALUES (1, 'Example Category', 'example-category');
        INSERT INTO government_offices (id, institution_id, district_id, name, is_demo)
            VALUES (1, 1, 1, 'Example Office', 1);
        INSERT INTO government_services (id, institution_id, category_id, name, slug, summary, is_demo)
            VALUES (1, 1, 1, 'Example Service', 'example-service', 'Example only', 1);
        INSERT INTO required_documents (id, service_id, name, source_id)
            VALUES (1, 1, 'Example Document', 1);
        INSERT INTO verification_records (service_id, section, last_edited_by_id)
            VALUES (1, 'fees', 1);
        """
    )


def check_structure(db):
    count = db.execute(
        "SELECT COUNT(*) FROM sqlite_master "
        "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    ).fetchone()[0]
    report(count == EXPECTED_TABLES, f"Schema has {EXPECTED_TABLES} tables (found {count})")

    problems = db.execute("PRAGMA foreign_key_check").fetchall()
    report(not problems, "Sample data has no broken foreign keys")

    rejected(db, "District cannot point to a region that does not exist",
             "INSERT INTO districts (name, region_id) VALUES ('Nowhere', 999)")


def check_verification(db):
    update = "UPDATE verification_records SET {} WHERE service_id = 1 AND section = 'fees'"

    rejected(db, "Cannot mark a section verified without source, date and checker",
             update.format("status = 'verified'"))

    rejected(db, "The last editor cannot verify their own change",
             update.format("status = 'verified', source_id = 1, last_checked_on = '2026-01-01', "
                           "review_due_on = '2026-07-01', verified_by_id = 1"))

    accepted(db, "A different person can verify the section",
             update.format("status = 'verified', source_id = 1, last_checked_on = '2026-01-01', "
                           "review_due_on = '2026-07-01', verified_by_id = 2"))

    rejected(db, "A service cannot have two records for one section",
             "INSERT INTO verification_records (service_id, section) VALUES (1, 'fees')")

    rejected(db, "An unknown section name is refused",
             "INSERT INTO verification_records (service_id, section) VALUES (1, 'gossip')")

    rejected(db, "A demonstration office can never be verified",
             "UPDATE government_offices SET verification_status = 'verified', source_id = 1, "
             "last_verified_on = '2026-01-01', review_due_on = '2026-07-01', verified_by_id = 2 "
             "WHERE id = 1")


def check_service_offices(db):
    accepted(db, "An office can be linked to a service as pending",
             "INSERT INTO service_offices (service_id, office_id) VALUES (1, 1)")

    rejected(db, "The same office cannot be linked to a service twice",
             "INSERT INTO service_offices (service_id, office_id) VALUES (1, 1)")

    rejected(db, "A claim that an office offers a service needs evidence to be verified",
             "UPDATE service_offices SET verification_status = 'verified' WHERE id = 1")


def check_fees_and_processing(db):
    fee = "INSERT INTO service_fees (service_id, fee_name, amount_ugx) VALUES (1, 'Example', ?)"
    accepted(db, "An unconfirmed fee is stored as empty (NULL)", fee, (None,))
    accepted(db, "A free service is stored as 0, which is different from empty", fee, (0,))
    rejected(db, "A negative fee is refused", fee, (-1,))

    rejected(db, "Minimum processing days cannot exceed the maximum",
             "INSERT INTO processing_information (service_id, min_working_days, max_working_days) "
             "VALUES (1, 10, 5)")


def check_input_safety(db):
    rejected(db, "A javascript: link is refused as a source (XSS protection)",
             "INSERT INTO official_sources (institution_id, title, url) "
             "VALUES (1, 'Bad', 'javascript:alert(1)')")

    rejected(db, "An office cannot have a latitude without a longitude",
             "UPDATE government_offices SET latitude = 2.0 WHERE id = 1")


def check_citizen_data(db):
    report_sql = ("INSERT INTO citizen_reports (reference_code, service_name, problem_type, "
                  "description, status) VALUES (?, 'Example Service', 'incorrect_fee', "
                  "'The example fee looks wrong.', ?)")
    accepted(db, "A citizen can submit a report", report_sql, ("CC-0001", "new"))
    rejected(db, "A report cannot be resolved without recording the action taken",
             report_sql, ("CC-0002", "resolved"))

    views = "INSERT INTO daily_views (view_date, service_id, institution_id) VALUES (?, ?, ?)"
    accepted(db, "A daily view row counts one service", views, ("2026-01-01", 1, None))
    rejected(db, "A service has only one view row per day", views, ("2026-01-01", 1, None))
    # A different date, so only the "exactly one thing" rule can refuse this.
    rejected(db, "A daily view row cannot count two things at once", views, ("2026-01-02", 1, 1))


def check_delete_rules(db):
    rejected(db, "A source in use cannot be deleted, so citations are never lost",
             "DELETE FROM official_sources WHERE id = 1")

    db.execute("INSERT INTO government_services (id, institution_id, category_id, name, slug, summary) "
               "VALUES (2, 1, 1, 'Temporary Service', 'temporary-service', 'Example only')")
    db.execute("INSERT INTO required_documents (service_id, name) VALUES (2, 'Temporary Document')")
    db.execute("DELETE FROM government_services WHERE id = 2")
    left = db.execute("SELECT COUNT(*) FROM required_documents WHERE service_id = 2").fetchone()[0]
    report(left == 0, "Deleting a service also removes its documents")


def check_status_logic():
    today = date(2026, 11, 6)
    yesterday = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)

    report(effective_status("verified", yesterday, today) == "outdated",
           "A verified record past its review date shows as outdated")
    report(effective_status("verified", tomorrow, today) == "verified",
           "A verified record before its review date stays verified")
    report(overall_status(["verified", "verified", "pending", "verified", "verified"]) == "pending",
           "One pending section makes the whole service pending")
    report(overall_status(["verified", "outdated", "pending"]) == "outdated",
           "Outdated outranks pending")


def main():
    db = sqlite3.connect(":memory:", isolation_level=None)
    # SQLite ignores foreign keys unless this is switched on for each connection.
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))
    add_sample_data(db)

    check_structure(db)
    check_verification(db)
    check_service_offices(db)
    check_fees_and_processing(db)
    check_input_safety(db)
    check_citizen_data(db)
    check_delete_rules(db)
    check_status_logic()
    db.close()

    passed = sum(results)
    print(f"\n{passed} of {len(results)} checks passed.")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
