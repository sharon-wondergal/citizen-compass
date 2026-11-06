"""Custom terminal commands, such as: flask seed categories"""

import click
from flask.cli import AppGroup

from seed.categories import seed_categories
from seed.demo import remove_demo_data, seed_demo_data

seed_commands = AppGroup("seed", help="Add starting data to the database.")


@seed_commands.command("categories")
def categories_command():
    """Add the standard service categories. Safe to run more than once."""
    added = seed_categories()
    click.echo(f"Added {added} categories.")


@seed_commands.command("demo")
def demo_command():
    """Add clearly fictional records for testing. Safe to run more than once."""
    added = seed_demo_data()
    click.echo(f"Added {added} demonstration services.")


@seed_commands.command("remove-demo")
def remove_demo_command():
    """Delete every demonstration record."""
    removed = remove_demo_data()
    click.echo(f"Removed {removed} demonstration services.")


def register_commands(app):
    app.cli.add_command(seed_commands)
