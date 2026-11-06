"""Stage 10 tests: administrator accounts, login and access control.

Every account and password here exists only inside these tests.
"""

import re
from datetime import datetime, timedelta

import pytest

from app import create_app
from app.config import TestingConfig
from app.extensions import db
from app.logic.auth import (
    LOCK_MINUTES,
    LOGIN_FAILED_MESSAGE,
    MAX_FAILED_LOGINS,
    authenticate,
    create_admin,
    is_safe_next,
    role_required,
    validate_new_password,
)
from app.models import AdminUser, AuditLog

EMAIL = "editor@example.com"
PASSWORD = "correct-horse-battery"
NOW = datetime(2026, 6, 1, 12, 0)


@pytest.fixture
def admin(database):
    return create_admin("Test Editor", EMAIL, PASSWORD, "editor")


def sign_in(client, email=EMAIL, password=PASSWORD, address="/admin/login"):
    return client.post(address, data={"email": email, "password": password})


# ---------- Passwords ----------

def test_password_is_stored_as_a_hash(admin):
    assert PASSWORD not in admin.password_hash
    assert admin.password_hash.startswith("scrypt:")


def test_password_check(admin):
    assert admin.check_password(PASSWORD) is True
    assert admin.check_password("wrong-password-here") is False


def test_same_password_gives_different_hashes(admin):
    second = create_admin("Second", "second@example.com", PASSWORD)
    assert admin.password_hash != second.password_hash


@pytest.mark.parametrize("password", ["short", "x" * 11, "y" * 129])
def test_weak_passwords_are_refused(password):
    with pytest.raises(ValueError, match="characters"):
        validate_new_password(password)


def test_email_cannot_be_the_password():
    with pytest.raises(ValueError, match="email"):
        validate_new_password("person@example.com", "person@example.com")


# ---------- Creating accounts ----------

def test_email_is_stored_in_lower_case(database):
    admin = create_admin("Test", "Person@Example.COM", PASSWORD)
    assert admin.email == "person@example.com"


def test_duplicate_email_is_refused(admin):
    with pytest.raises(ValueError, match="already exists"):
        create_admin("Other", EMAIL.upper(), PASSWORD)


@pytest.mark.parametrize("name, email, role, message", [
    ("", EMAIL, "editor", "name"),
    ("Test", "not-an-email", "editor", "valid"),
    ("Test", EMAIL, "emperor", "role"),
])
def test_invalid_accounts_are_refused(database, name, email, role, message):
    with pytest.raises(ValueError, match=message):
        create_admin(name, email, PASSWORD, role)


def test_admin_command_creates_an_account(app, database):
    result = app.test_cli_runner().invoke(
        args=["admin", "create", "--name", "Test", "--email", EMAIL, "--role", "verifier"],
        input=f"{PASSWORD}\n{PASSWORD}\n",
    )
    assert result.exit_code == 0
    assert "Created verifier account" in result.output
    assert PASSWORD not in result.output
    assert db.session.query(AdminUser).one().role == "verifier"


def test_admin_command_explains_a_weak_password(app, database):
    result = app.test_cli_runner().invoke(
        args=["admin", "create", "--name", "Test", "--email", EMAIL, "--role", "editor"],
        input="short\nshort\n",
    )
    assert result.exit_code != 0
    assert "at least 12 characters" in result.output
    assert db.session.query(AdminUser).count() == 0


def test_admin_list_never_shows_password_hashes(app, admin):
    result = app.test_cli_runner().invoke(args=["admin", "list"])
    assert EMAIL in result.output
    assert "scrypt" not in result.output


# ---------- Signing in ----------

def test_correct_login_opens_the_dashboard(client, admin):
    response = sign_in(client)
    assert response.status_code == 302
    assert response.headers["Location"] == "/admin"
    assert client.get("/admin").status_code == 200


def test_email_is_not_case_sensitive(client, admin):
    assert sign_in(client, email=EMAIL.upper()).status_code == 302


@pytest.mark.parametrize("email, password", [
    (EMAIL, "wrong-password-here"),
    ("nobody@example.com", PASSWORD),
])
def test_failed_logins_give_the_same_message(client, admin, email, password):
    response = sign_in(client, email, password)
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "We couldn&#39;t sign you in." in text
    assert client.get("/admin").status_code == 302


def test_empty_login_shows_field_errors(client, admin):
    text = sign_in(client, "", "").get_data(as_text=True)
    assert "Enter your email address." in text
    assert "Enter your password." in text


def test_successful_login_is_recorded(client, admin):
    sign_in(client)
    entry = db.session.query(AuditLog).one()

    assert entry.action == "login"
    assert entry.admin_user_id == admin.id
    assert PASSWORD not in (entry.new_values or "")
    assert admin.last_login_at is not None


def test_signed_in_admin_skips_the_login_page(client, admin):
    sign_in(client)
    assert client.get("/admin/login").status_code == 302


def test_session_cookie_is_protected(client, admin):
    cookie = sign_in(client).headers["Set-Cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie


# ---------- Lockout ----------

def fail_logins(count, now=NOW):
    for _ in range(count):
        assert authenticate(EMAIL, "wrong-password-here", now) is None


def test_account_locks_after_repeated_failures(admin):
    fail_logins(MAX_FAILED_LOGINS)
    assert admin.locked_until == NOW + timedelta(minutes=LOCK_MINUTES)
    assert authenticate(EMAIL, PASSWORD, NOW + timedelta(minutes=1)) is None


def test_account_unlocks_after_the_wait(admin):
    fail_logins(MAX_FAILED_LOGINS)
    later = NOW + timedelta(minutes=LOCK_MINUTES + 1)
    assert authenticate(EMAIL, PASSWORD, later) is admin


def test_fewer_failures_do_not_lock(admin):
    fail_logins(MAX_FAILED_LOGINS - 1)
    assert authenticate(EMAIL, PASSWORD, NOW) is admin


def test_success_resets_the_failure_count(admin):
    fail_logins(MAX_FAILED_LOGINS - 1)
    authenticate(EMAIL, PASSWORD, NOW)
    assert admin.failed_login_count == 0


def test_locked_account_gives_the_usual_message(client, admin):
    fail_logins(MAX_FAILED_LOGINS, datetime.now())
    assert LOGIN_FAILED_MESSAGE.replace("'", "&#39;") in sign_in(client).get_data(as_text=True)


def test_inactive_account_cannot_sign_in(admin):
    admin.is_active = False
    db.session.commit()
    assert authenticate(EMAIL, PASSWORD) is None


def test_too_many_login_attempts_are_slowed_down(monkeypatch):
    monkeypatch.setattr(TestingConfig, "RATELIMIT_ENABLED", True)
    limited_app = create_app("testing")

    with limited_app.app_context():
        db.create_all()
        client = limited_app.test_client()
        statuses = [sign_in(client).status_code for _ in range(11)]
        db.session.remove()
        db.drop_all()

    assert statuses[:10] == [200] * 10
    assert statuses[10] == 429


# ---------- Access control ----------

def test_dashboard_requires_login(client, database):
    response = client.get("/admin")
    assert response.status_code == 302
    assert "/admin/login" in response.headers["Location"]


def test_login_returns_to_the_requested_page(client, admin):
    assert sign_in(client, address="/admin/login?next=/admin").headers["Location"] == "/admin"


@pytest.mark.parametrize("target", [
    "https://evil.example", "//evil.example", "/\\evil.example", "javascript:alert(1)",
    "", None,
])
def test_unsafe_redirects_are_refused(target):
    assert is_safe_next(target) is False


def test_local_redirect_is_allowed():
    assert is_safe_next("/admin") is True


def test_login_ignores_an_outside_redirect(client, admin):
    response = sign_in(client, address="/admin/login?next=https://evil.example")
    assert response.headers["Location"] == "/admin"


def test_deactivated_admin_loses_access_at_once(client, admin):
    sign_in(client)
    admin.is_active = False
    db.session.commit()
    assert client.get("/admin").status_code == 302


def add_protected_route(app):
    app.add_url_rule(
        "/admin/test-area",
        endpoint="test_area",
        view_func=role_required("super_admin")(lambda: "secret area"),
    )


def test_wrong_role_is_refused(app, client, admin):
    add_protected_route(app)
    sign_in(client)
    response = client.get("/admin/test-area")

    assert response.status_code == 403
    assert "You can't open this page" in response.get_data(as_text=True)


def test_right_role_is_allowed(app, client, database):
    add_protected_route(app)
    create_admin("Boss", "boss@example.com", PASSWORD, "super_admin")
    sign_in(client, "boss@example.com")
    assert client.get("/admin/test-area").status_code == 200


def test_role_check_requires_login_first(app, client, database):
    add_protected_route(app)
    assert client.get("/admin/test-area").status_code == 302


# ---------- Signing out ----------

def test_sign_out_ends_the_session(client, admin):
    sign_in(client)
    response = client.post("/admin/logout", follow_redirects=True)

    assert "You&#39;ve signed out." in response.get_data(as_text=True)
    assert client.get("/admin").status_code == 302


def test_sign_out_cannot_be_triggered_by_a_link(client, admin):
    sign_in(client)
    assert client.get("/admin/logout").status_code == 405
    assert client.get("/admin").status_code == 200


# ---------- CSRF protection, switched on as in real use ----------

@pytest.fixture
def csrf_client(monkeypatch):
    monkeypatch.setattr(TestingConfig, "WTF_CSRF_ENABLED", True)
    protected_app = create_app("testing")
    with protected_app.app_context():
        db.create_all()
        create_admin("Test Editor", EMAIL, PASSWORD)

    # Requests run outside the block above, as they do on a real server.
    # Each one then gets its own context, and so its own form token.
    yield protected_app.test_client()

    with protected_app.app_context():
        db.session.remove()
        db.drop_all()


def page_token(client, address):
    text = client.get(address).get_data(as_text=True)
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', text).group(1)


def test_login_without_a_token_is_refused(csrf_client):
    response = sign_in(csrf_client)
    assert response.status_code == 400
    assert "Please try again" in response.get_data(as_text=True)


def test_login_with_a_token_works(csrf_client):
    token = page_token(csrf_client, "/admin/login")
    response = csrf_client.post(
        "/admin/login", data={"email": EMAIL, "password": PASSWORD, "csrf_token": token}
    )
    assert response.status_code == 302


def test_sign_out_needs_a_token(csrf_client):
    token = page_token(csrf_client, "/admin/login")
    csrf_client.post(
        "/admin/login", data={"email": EMAIL, "password": PASSWORD, "csrf_token": token}
    )
    assert csrf_client.post("/admin/logout").status_code == 400
    assert csrf_client.get("/admin").status_code == 200

    token = page_token(csrf_client, "/admin")
    assert csrf_client.post("/admin/logout", data={"csrf_token": token}).status_code == 302
    assert csrf_client.get("/admin").status_code == 302


# ---------- Private pages ----------

@pytest.mark.parametrize("address", ["/admin", "/admin/login"])
def test_admin_pages_are_not_stored(client, admin, address):
    if address == "/admin":
        sign_in(client)
    headers = client.get(address).headers
    assert headers["Cache-Control"] == "no-store"
    assert headers["X-Robots-Tag"] == "noindex"


def test_public_pages_do_not_advertise_the_admin_area(client, database):
    assert "/admin" not in client.get("/").get_data(as_text=True)


def test_public_pages_still_work_while_signed_in(client, admin):
    sign_in(client)
    assert client.get("/").status_code == 200
