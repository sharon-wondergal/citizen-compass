"""A permanent record of administrative actions."""

import json

from app.extensions import db
from app.models import AuditLog


def to_json(values):
    return None if values is None else json.dumps(values, default=str, sort_keys=True)


def record_audit(admin, action, table_name, record_id=None, label=None, old=None, new=None):
    """Add an audit entry. The caller commits it with the change it describes.

    Saving both together means a change can't happen without its history.
    Never pass passwords or password hashes here.
    """
    db.session.add(AuditLog(
        admin_user_id=admin.id if admin else None,
        action=action,
        table_name=table_name,
        record_id=record_id,
        record_label=label,
        old_values=to_json(old),
        new_values=to_json(new),
    ))
