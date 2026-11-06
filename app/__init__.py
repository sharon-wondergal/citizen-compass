"""The application factory.

create_app() builds a configured application on request. Tests can then make
their own app with a temporary database, separate from the development one.
"""

from flask import Flask

from app.blueprints.main import main_bp
from app.config import get_config, validate_config
from app.extensions import csrf, db, limiter, migrate


def create_app(config_name=None):
    # instance_relative_config keeps the SQLite file in the private instance/ folder.
    app = Flask(__name__, instance_relative_config=True)

    app.config.from_object(get_config(config_name))
    validate_config(app)

    register_extensions(app)
    register_blueprints(app)

    return app


def register_extensions(app):
    db.init_app(app)
    # Batch mode lets migrations change existing SQLite tables.
    migrate.init_app(app, db, render_as_batch=True)
    csrf.init_app(app)
    limiter.init_app(app)


def register_blueprints(app):
    app.register_blueprint(main_bp)
