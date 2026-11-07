# Citizen Compass – Uganda

**Know Before You Go.**

Citizen Compass is a government service preparation platform. It helps citizens check what documents they need, what a service costs, where to go and how long it takes, before they travel to a government office.

> Citizen Compass is an independent university project. It is not a government website, and it does not process applications or payments.

## Project status

Under development, stage by stage. The citizen pages work: homepage, service search, preparation checklists, the institution directory and the office finder. The only records so far are fictional demonstrations.

| Stage | Topic | Status |
|---|---|---|
| 1 | Requirements and architecture | Done |
| 2 | Database design and ERD | Done: see [docs/database-design.md](docs/database-design.md) |
| 3 | PyCharm project and virtual environment | Done |
| 4 | Flask configuration | Done |
| 5 | Database models and relationships | Done |
| 6 | Homepage and navigation | Done |
| 7 | Service directory and search | Done |
| 8 | Service preparation checklist | Done |
| 9 | Institution and office directories | Done |
| 10 | Administrator login and dashboard | Done |
| 11A | Managing records from the admin area | Done |
| 11B | Verification workflow | Paused while the prototype is presented |

## Presenting the prototype

The citizen pages are ready to present, with real services and fictional examples:

```bash
flask seed real
flask seed presentation
flask run
```

Then open <http://127.0.0.1:5000>.

- `flask seed real` adds seven real services, entered from official pages on 7 November 2026. They're all pending verification, and fee amounts stay hidden from citizens until a second person checks them.
- `flask seed presentation` adds fictional records labelled "Demonstration only". Remove them with `flask seed remove-demo`.

## Requirements

- Python 3.14 (the installed package versions were tested on 3.14.2)
- PyCharm
- Git

## Setup on a new computer

Run these commands in the PyCharm Terminal, from the project folder.

1. Create the virtual environment:

   ```bash
   python -m venv .venv
   ```

2. Activate it (Windows PowerShell):

   ```bash
   .\.venv\Scripts\Activate.ps1
   ```

3. Install the packages:

   ```bash
   python -m pip install -r requirements.txt
   ```

4. Create your private settings file:

   ```bash
   Copy-Item .env.example .env
   ```

5. Create a secret key, then paste it into `.env` as the `SECRET_KEY` value:

   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

6. Create the database tables:

   ```bash
   flask db upgrade
   ```

7. Add the standard service categories:

   ```bash
   flask seed categories
   ```

8. Optional: add fictional demonstration records for testing:

   ```bash
   flask seed demo
   ```

   Remove them at any time with `flask seed remove-demo`. They aren't real government information.

9. Create an administrator. You'll be asked for a password, which stays hidden as you type:

   ```bash
   flask admin create
   ```

   Roles are `editor`, `verifier` and `super_admin`. Sign in at `/admin/login`.

## Run the application

```bash
flask run
```

Then open <http://127.0.0.1:5000> in your browser. Press Ctrl+C in the terminal to stop it.

## Run the tests

```bash
python -m pytest
```

## Check the setup

```bash
python docs/check_setup.py
python docs/check_schema.py
```

## Technology

Python, Flask, SQLAlchemy, SQLite, Jinja2, Bootstrap 5 and JavaScript.
