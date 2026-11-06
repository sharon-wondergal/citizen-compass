"""Flask extensions, created once and shared by the whole application.

They are created here without an app, then connected to one in create_app().
Keeping them in their own file stops circular imports: models and routes can
import db from here without importing the application itself.
"""

import sqlite3

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from sqlalchemy import MetaData, event
from sqlalchemy.engine import Engine

# Predictable constraint names. Migrations need a name to change a constraint later.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

db = SQLAlchemy(metadata=MetaData(naming_convention=NAMING_CONVENTION))
migrate = Migrate()
csrf = CSRFProtect()

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Please sign in to continue."
# End the session if it appears to move to a different browser or connection.
login_manager.session_protection = "strong"

limiter = Limiter(key_func=get_remote_address)


@event.listens_for(Engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    """Switch on foreign key checks for every new SQLite connection.

    SQLite ignores foreign keys unless this is set on each connection, so the
    relationships designed in Stage 2 would not be enforced without it.
    """
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()
