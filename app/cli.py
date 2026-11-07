"""Custom terminal commands, such as: flask seed categories"""

import click
from flask.cli import AppGroup
from sqlalchemy import select

from app.extensions import db
from app.logic.auth import create_admin
from app.models import AdminUser
from app.models.base import ADMIN_ROLES
from seed.categories import seed_categories
from seed.demo import remove_demo_data, seed_demo_data
from seed.presentation import seed_presentation_data
from seed.real_services import seed_real_services

seed_commands = AppGroup("seed", help="Add starting data to the database.")
admin_commands = AppGroup("admin", help="Manage administrator accounts.")


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


@seed_commands.command("presentation")
def presentation_command():
    """Add a fuller set of fictional records for presenting the prototype."""
    added = seed_presentation_data()
    click.echo(f"Added {added} more demonstration services.")


@seed_commands.command("real")
def real_command():
    """Add real services from official sources, all pending verification."""
    added = seed_real_services()
    click.echo(f"Added {added} real services. All are pending verification.")


@seed_commands.command("remove-demo")
def remove_demo_command():
    """Delete every demonstration record."""
    removed = remove_demo_data()
    click.echo(f"Removed {removed} demonstration services.")


@admin_commands.command("create")
@click.option("--name", prompt="Full name")
@click.option("--email", prompt="Email address")
@click.option("--role", type=click.Choice(ADMIN_ROLES), default="editor", prompt="Role")
@click.password_option("--password", help="Leave this out to be asked privately.")
def create_admin_command(name, email, role, password):
    """Create an administrator. The password is typed privately."""
    try:
        admin = create_admin(name, email, password, role)
    except ValueError as error:
        raise click.ClickException(str(error)) from error
    click.echo(f"Created {admin.role} account for {admin.email}.")


@admin_commands.command("list")
def list_admins_command():
    """Show administrator accounts. Passwords are never shown."""
    admins = db.session.scalars(select(AdminUser).order_by(AdminUser.email)).all()
    if not admins:
        click.echo("No administrators yet.")
    for admin in admins:
        state = "active" if admin.is_active else "inactive"
        click.echo(f"{admin.email} | {admin.role} | {state}")


def register_commands(app):
    app.cli.add_command(seed_commands)
    app.cli.add_command(admin_commands)
