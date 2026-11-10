"""The application factory.

create_app() builds a configured application on request. Tests can then make
their own app with a temporary database, separate from the development one.
"""

from flask import Flask

from app import models  # noqa: F401 - loading the models registers the tables
from app.blueprints import (  # noqa: F401 - loading these adds their admin routes
    admin_directory,
    admin_reports,
    admin_services,
    admin_verification,
)
from app.blueprints.admin import admin_bp
from app.blueprints.auth import auth_bp
from app.blueprints.directory import directory_bp
from app.blueprints.main import main_bp
from app.blueprints.reports import reports_bp
from app.blueprints.services import services_bp
from app.cli import register_commands
from app.config import get_config, validate_config
from app.errors import register_error_handlers
from app.extensions import csrf, db, limiter, login_manager, migrate
from app.template_helpers import register_template_helpers


def create_app(config_name=None):
    # instance_relative_config keeps the SQLite file in the private instance/ folder.
    app = Flask(__name__, instance_relative_config=True)

    app.config.from_object(get_config(config_name))
    validate_config(app)

    register_extensions(app)
    register_blueprints(app)
    register_error_handlers(app)
    register_template_helpers(app)
    register_commands(app)

    return app


def register_extensions(app):
    db.init_app(app)
    # Batch mode lets migrations change existing SQLite tables.
    migrate.init_app(app, db, render_as_batch=True)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)


def register_blueprints(app):
    app.register_blueprint(main_bp)
    app.register_blueprint(services_bp)
    app.register_blueprint(directory_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
