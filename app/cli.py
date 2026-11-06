"""Custom terminal commands, such as: flask seed categories"""

import click
from flask.cli import AppGroup

from seed.categories import seed_categories

seed_commands = AppGroup("seed", help="Add starting data to the database.")


@seed_commands.command("categories")
def categories_command():
    """Add the standard service categories. Safe to run more than once."""
    added = seed_categories()
    click.echo(f"Added {added} categories.")


def register_commands(app):
    app.cli.add_command(seed_commands)
