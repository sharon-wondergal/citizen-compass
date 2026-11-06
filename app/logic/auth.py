"""Administrator accounts, login rules and role checks."""

from datetime import UTC, datetime, timedelta
from functools import lru_cache, wraps
from urllib.parse import urlsplit

from email_validator import EmailNotValidError, validate_email
from flask import abort
from flask_login import current_user, login_required
from sqlalchemy import select
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db, login_manager
from app.models import AdminUser
from app.models.base import ADMIN_ROLES

MAX_FAILED_LOGINS = 5
LOCK_MINUTES = 15
MINIMUM_PASSWORD_LENGTH = 12
MAXIMUM_PASSWORD_LENGTH = 128

ROLE_LABELS = {
    "editor": "Editor",
    "verifier": "Verifier",
    "super_admin": "Super administrator",
}

# One message for every failure, so nobody can use it to discover which
# email addresses have accounts.
LOGIN_FAILED_MESSAGE = (
    "We couldn't sign you in. Check your details, or try again later if your "
    "account has been locked."
)


def utc_now():
    """The current time in UTC, stored without a time zone in SQLite."""
    return datetime.now(UTC).replace(tzinfo=None)


@lru_cache(maxsize=1)
def spare_hash():
    return generate_password_hash("not-a-real-password")


def waste_equal_time(password):
    """Do the same work as a real check, so timing can't reveal real accounts."""
    check_password_hash(spare_hash(), password)


@login_manager.user_loader
def load_user(user_id):
    """Find the signed-in administrator on each request."""
    user = db.session.get(AdminUser, int(user_id))
    return user if user is not None and user.is_active else None


def find_admin(email):
    return db.session.scalar(select(AdminUser).filter_by(email=email.strip().lower()))


def authenticate(email, password, now=None):
    """Return the administrator if the details are right, otherwise None."""
    now = now or utc_now()
    user = find_admin(email)

    if user is None or not user.is_active:
        waste_equal_time(password)
        return None

    if user.locked_until and user.locked_until > now:
        waste_equal_time(password)
        return None

    if user.check_password(password):
        user.failed_login_count = 0
        user.locked_until = None
        user.last_login_at = now
        db.session.commit()
        return user

    user.failed_login_count += 1
    if user.failed_login_count >= MAX_FAILED_LOGINS:
        user.locked_until = now + timedelta(minutes=LOCK_MINUTES)
        user.failed_login_count = 0
    db.session.commit()
    return None


def is_safe_next(target):
    """Only allow redirects within this site after login.

    Otherwise a crafted link could send someone to a fake site after signing in.
    """
    if not target or not target.startswith("/") or target.startswith("//"):
        return False
    if "\\" in target:
        return False
    parts = urlsplit(target)
    return not parts.scheme and not parts.netloc


def role_required(*roles):
    """Only allow administrators with one of these roles."""

    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if not current_user.has_role(*roles):
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


def validate_new_password(password, email=""):
    """Raise ValueError if a new password is too weak."""
    if len(password) < MINIMUM_PASSWORD_LENGTH:
        raise ValueError(f"Passwords must have at least {MINIMUM_PASSWORD_LENGTH} characters.")
    if len(password) > MAXIMUM_PASSWORD_LENGTH:
        raise ValueError(f"Passwords can have at most {MAXIMUM_PASSWORD_LENGTH} characters.")
    if email and password.lower() == email.lower():
        raise ValueError("The password can't be the same as the email address.")


def create_admin(full_name, email, password, role="editor"):
    """Create an administrator, or raise ValueError with a clear reason."""
    full_name = full_name.strip()
    if not full_name:
        raise ValueError("Please enter a name.")
    if role not in ADMIN_ROLES:
        raise ValueError(f"The role must be one of: {', '.join(ADMIN_ROLES)}.")

    try:
        email = validate_email(email, check_deliverability=False).normalized.lower()
    except EmailNotValidError as error:
        raise ValueError(f"That email address isn't valid: {error}") from error

    if find_admin(email):
        raise ValueError("An administrator with that email address already exists.")
    validate_new_password(password, email)

    admin = AdminUser(full_name=full_name, email=email, role=role)
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()
    return admin
