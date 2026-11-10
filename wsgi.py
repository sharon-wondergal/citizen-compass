"""The entry point for a production web server, such as gunicorn or waitress.

Hosting services look for an object called "application" or "app" in a file
like this one. run.py is for local development with "flask run".
"""

from app import create_app

app = application = create_app()
