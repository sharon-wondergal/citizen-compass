"""A permanent history of administrative changes. Rows are only ever added."""

from sqlalchemy import Index

from app.extensions import db
from app.models.base import AUDIT_ACTIONS, choice_check


class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    __table_args__ = (
        choice_check("action", AUDIT_ACTIONS),
        Index("ix_audit_logs_record", "table_name", "record_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    admin_user_id = db.Column(db.Integer, db.ForeignKey("admin_users.id", ondelete="RESTRICT"))
    action = db.Column(db.String(20), nullable=False)
    table_name = db.Column(db.String(50), nullable=False)
    record_id = db.Column(db.Integer)
    record_label = db.Column(db.String(200))
    old_values = db.Column(db.Text)  # JSON text.
    new_values = db.Column(db.Text)  # JSON text.
    created_at = db.Column(
        db.DateTime, nullable=False, server_default=db.func.current_timestamp(), index=True
    )

    admin_user = db.relationship("AdminUser")

    def __repr__(self):
        return f"<AuditLog {self.action} {self.table_name}>"
