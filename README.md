# Citizen Compass – Uganda

**Know Before You Go.**

Citizen Compass is a government service preparation platform. It helps citizens check what documents they need, what a service costs, where to go and how long it takes, before they travel to a government office.

Its main idea isn't more information. It's information turned into a verified, structured checklist, where every section shows its official source and when it was last checked, and where an unconfirmed fee is never shown as fact.

> Citizen Compass is an independent university project. It is not a government website, and it does not process applications or payments.

## Features

**For citizens**, with no account needed:

- **Quick answers:** ask one question on the homepage and see documents, fee, nearest office and time.
- **Search:** filter by category, institution, region, district, how a service is provided, and verification status.
- **Six-field checklists:** service information, documents, fees, offices, processing time, and sources and verification.
- **Situations:** a citizen picks theirs, such as adult or minor, and sees the documents for it.
- **Preparation tools:** tick off documents, see progress, print or save as PDF, and share.
- **Directories:** browse institutions, and find offices with your district shown first.
- **Reports:** report incorrect information and receive a reference code.

**For administrators:**

- **Secure access:** sign in with one of three roles: editor, verifier and super administrator.
- **Dashboard:** totals, verification status and recent changes.
- **Managing records:** services, documents, fees, steps, offices, institutions, sources, categories, regions and districts.
- **Verification workflow:** a review queue, and separate approval so nobody verifies their own work.
- **Citizen reports:** review, resolve and reopen them.
- **History and analytics:** a full audit trail, plus analytics on searches, views, reports and outdated information.

**For other applications:**

- **Read-only JSON API:** under `/api/v1`. See [docs/architecture.md](docs/architecture.md).

## Technology

Python, Flask, SQLAlchemy, SQLite, Jinja2, Bootstrap 5 and plain JavaScript. Bootstrap and its icons are stored in the project, so the site doesn't depend on another website.

## Setup on a new computer

Run these in the PyCharm Terminal, from the project folder.

1. Create and activate the virtual environment:

   ```bash
   python -m venv .venv
   ```

   ```bash
   .\.venv\Scripts\Activate.ps1
   ```

2. Install the packages:

   ```bash
   python -m pip install -r requirements.txt
   ```

3. Create your private settings file, then put a new secret key in it:

   ```bash
   Copy-Item .env.example .env
   ```

   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

4. Create the database and add starting data:

   ```bash
   flask db upgrade
   flask seed categories
   flask seed real
   ```

5. Create an administrator. The password stays hidden as you type:

   ```bash
   flask admin create
   ```

## Run the application

```bash
flask run
```

Open <http://127.0.0.1:5000>. Administrators sign in at <http://127.0.0.1:5000/admin/login>. The site runs only while this command is running, so press **Ctrl+C** to stop it.

## Commands

| Command | What it does |
|---|---|
| `flask seed categories` | Adds the 14 service categories |
| `flask seed real` | Adds seven real services, read from official pages on 7 November 2026 and all pending verification |
| `flask seed presentation` | Adds fictional records labelled "Demonstration only", for testing |
| `flask seed remove-demo` | Deletes every fictional record |
| `flask admin create` | Creates an administrator |
| `flask admin list` | Lists administrators, without passwords |
| `flask privacy-cleanup` | Blanks old report contacts and deletes old searches |
| `flask db upgrade` | Applies database changes |

## Tests

```bash
python -m pytest
```

All 682 tests should pass. They use a temporary database, so they never touch your data. The design checks from Stage 2 also still run:

```bash
python docs/check_schema.py
```

pytest shows a warning that WTForms 3.4 will change how menu choices are written. The project pins WTForms 3.3.2, so it only matters if the package is upgraded.

## About the information

The seven real services were entered only from official agency pages, and each row links to its source. Anything the sources didn't state is shown as "Not confirmed". No section has been verified yet. A second person must check each one against its source before fees appear to citizens, and agencies change their requirements, so the information needs regular review.

## Documentation

| Document | Contents |
|---|---|
| [docs/architecture.md](docs/architecture.md) | Layers, blueprints, trust model, API, security and testing |
| [docs/database-design.md](docs/database-design.md) | Every table, relationship and rule |
| [docs/erd.mmd](docs/erd.mmd) | The entity relationship diagram |
| [docs/deployment.md](docs/deployment.md) | Putting the site online, and keeping it running |

## Development stages

| Stage | Topic | Status |
|---|---|---|
| 1 | Requirements and architecture | Done |
| 2 | Database design and ERD | Done |
| 3 | Project setup and virtual environment | Done |
| 4 | Flask configuration | Done |
| 5 | Database models and relationships | Done |
| 6 | Homepage and navigation | Done |
| 7 | Service directory and search | Done |
| 8 | Service preparation checklist | Done |
| 9 | Institution and office directories | Done |
| 10 | Administrator login and dashboard | Done |
| 11 | Record management and verification workflow | Done |
| 12 | Citizen reports, their review, and analytics | Done |
| 13 | JSON API | Done |
| 14 | Testing, debugging and security | Done |
| 15 | UI refinement and deployment preparation | Done |
