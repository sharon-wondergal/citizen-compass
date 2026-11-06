"""Administrator accounts. Login behaviour is added in Stage 10."""

from sqlalchemy import text

from app.extensions import db
from app.models.base import ADMIN_ROLES, TimestampMixin, choice_check, flag, minimum_check


class AdminUser(TimestampMixin, db.Model):
    __tablename__ = "admin_users"
    __table_args__ = (
        choice_check("role", ADMIN_ROLES),
        minimum_check("failed_login_count", 0, nullable=False),
    )

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="editor", server_default="editor")
    is_active = flag(True)
    failed_login_count = db.Column(
        db.Integer, nullable=False, default=0, server_default=text("0")
    )
    locked_until = db.Column(db.DateTime)
    last_login_at = db.Column(db.DateTime)

    def __repr__(self):
        return f"<AdminUser {self.email}>"
