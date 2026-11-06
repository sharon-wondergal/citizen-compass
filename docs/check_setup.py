"""Stage 3 setup check for Citizen Compass.

Confirms the virtual environment, packages and private settings are ready.

Run it from the project folder, with the virtual environment active:

    python docs/check_setup.py

It never prints your secret key.
"""

import importlib
import importlib.metadata
import os
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Package name as installed, and the name used in an import statement.
PACKAGES = [
    ("Flask", "flask"),
    ("Flask-SQLAlchemy", "flask_sqlalchemy"),
    ("Flask-Migrate", "flask_migrate"),
    ("Flask-Login", "flask_login"),
    ("Flask-WTF", "flask_wtf"),
    ("Flask-Limiter", "flask_limiter"),
    ("python-dotenv", "dotenv"),
    ("email-validator", "email_validator"),
    ("pytest", "pytest"),
]

PLACEHOLDER_KEY = "replace-with-a-long-random-value"
MINIMUM_KEY_LENGTH = 32

results = []


def report(passed, description):
    results.append(passed)
    print(f"[{'PASS' if passed else 'FAIL'}] {description}")


def check_python():
    report(sys.prefix != sys.base_prefix, "Virtual environment is active")
    version = ".".join(str(part) for part in sys.version_info[:3])
    report(sys.version_info >= (3, 14), f"Python version is 3.14 or newer ({version})")


def check_packages():
    for package_name, import_name in PACKAGES:
        try:
            importlib.import_module(import_name)
            version = importlib.metadata.version(package_name)
            report(True, f"{package_name} {version} imports correctly")
        except Exception as error:  # Any failure here means the package is unusable.
            report(False, f"{package_name} failed to import: {error}")


def check_flask_stack():
    """Run the main packages together, not only one at a time."""
    try:
        from flask import Flask
        from flask_login import LoginManager
        from flask_sqlalchemy import SQLAlchemy
        from sqlalchemy import text

        app = Flask(__name__)
        app.config["SECRET_KEY"] = "setup-check-only"
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        db = SQLAlchemy(app)
        LoginManager(app)

        @app.route("/")
        def home():
            return "ok"

        with app.app_context():
            database_answer = db.session.execute(text("SELECT 1")).scalar()
            db.session.remove()
            db.engine.dispose()  # Close the temporary database connection.

        response = app.test_client().get("/")
        report(response.status_code == 200 and database_answer == 1,
               "Flask, SQLAlchemy and Flask-Login work together")
    except Exception as error:
        report(False, f"Flask packages failed together: {error}")


def check_settings():
    try:
        from dotenv import dotenv_values
    except ImportError:
        report(False, "Cannot read .env because python-dotenv is not installed")
        return

    env_file = PROJECT_ROOT / ".env"
    report(env_file.exists(), ".env file exists")
    if not env_file.exists():
        return

    settings = dotenv_values(env_file)
    secret_key = settings.get("SECRET_KEY") or ""
    report(len(secret_key) >= MINIMUM_KEY_LENGTH and secret_key != PLACEHOLDER_KEY,
           "SECRET_KEY is set to a long private value")
    report(bool(settings.get("DATABASE_URL")), "DATABASE_URL is set")


def check_git():
    git_path = shutil.which("git")
    if git_path:
        report(True, "Git is installed")
        report((PROJECT_ROOT / ".git").exists(), "Project is a Git repository")
    else:
        report(False, "Git is installed (get it from https://git-scm.com/download/win)")


def main():
    os.chdir(PROJECT_ROOT)
    check_python()
    check_packages()
    check_flask_stack()
    check_settings()
    check_git()

    passed = sum(results)
    print(f"\n{passed} of {len(results)} checks passed.")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
