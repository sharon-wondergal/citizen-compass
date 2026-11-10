# Citizen Compass – Uganda: Deployment Guide

**Stage 15 deliverable.** How to move Citizen Compass from your computer to a live web address.

## 1. Before going public

A live site is used by real citizens, so check these first. Items marked **(you)** can't be done by code.

| Check | Why it matters |
|---|---|
| **(you)** Every real service checked against its source by a second person | Unverified sections show warnings, and fees stay hidden until verified |
| **(you)** Privacy notice reviewed, and registration with Uganda's Personal Data Protection Office considered | The site collects search text and optional contact details |
| **(you)** A real contact address set as `CONTACT_EMAIL` | The footer says contact details will be added before launch |
| **(you)** Supervisor or institution approval, if your university requires it | The site is public and names real government agencies |
| A new `SECRET_KEY`, used nowhere else | Signs login sessions and form tokens |
| `APP_ENV=production` and `FLASK_DEBUG=0` | The app refuses to start in production with debug mode on |
| HTTPS | Production sends login cookies over HTTPS only |
| No demonstration records | Run `flask seed remove-demo` if any were added |

## 2. Production settings

Create a `.env` file on the server. Never copy your development `.env`.

```text
APP_ENV=production
FLASK_DEBUG=0
SECRET_KEY=<a new value from: python -c "import secrets; print(secrets.token_hex(32))">
DATABASE_URL=sqlite:////full/path/to/citizen_compass.db
CONTACT_EMAIL=<a real address>
TRUST_PROXY=1
```

Set `TRUST_PROXY=1` only if your host puts its own proxy in front of the app. Most hosting services do.

## 3. Option A: PythonAnywhere

PythonAnywhere runs Flask apps with SQLite and offers a free account, which suits a university project. Menu names can change, so follow their current help pages alongside these steps.

1. Create an account, then open a **Bash console**.
2. Copy the project from GitHub:

   ```bash
   git clone https://github.com/sharon-wondergal/citizen-compass.git
   cd citizen-compass
   ```

3. Create a virtual environment with the newest Python they offer, and install the packages:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

   The pinned versions were tested on Python 3.14. If the host's Python is older and an install fails, tell your developer, so the versions can be adjusted and the tests re-run.

4. Create the production `.env` from section 2, then set up the database:

   ```bash
   flask db upgrade
   flask seed categories
   flask seed real
   flask admin create
   ```

5. On the **Web** tab, add a new web app with **Manual configuration**, and set the virtual environment path to the project's `.venv`.
6. Edit the WSGI configuration file they give you, so it contains:

   ```python
   import sys
   sys.path.insert(0, "/home/YOUR-USERNAME/citizen-compass")
   from wsgi import application
   ```

7. Add a static files mapping from `/static/` to the project's `app/static` folder, so the web server sends CSS and images directly.
8. Turn on **Force HTTPS**, then reload the web app.

## 4. Option B: a Linux server of your own

Install gunicorn in the virtual environment and run:

```bash
pip install gunicorn
gunicorn --workers 2 --bind 127.0.0.1:8000 wsgi:app
```

Put a web server such as nginx in front of it for HTTPS, and set `TRUST_PROXY=1`. With more than one worker, set `RATELIMIT_STORAGE_URI` to shared storage such as Redis, otherwise each worker counts requests separately.

## 5. Keeping it running

| Task | How often | Command |
|---|---|---|
| Remove old personal data | Daily, as a scheduled task | `flask privacy-cleanup` |
| Back up the database | Daily | Copy the `.db` file somewhere safe. SQLite copies are safest while the site is quiet |
| Clear the review queue | Weekly | Sign in and open **Verification** |
| Read citizen reports | Weekly | Sign in and open **Reports** |
| Apply database changes after an update | After each update | `git pull`, then `flask db upgrade`, then reload |

## 6. After launch

- Open the site on a phone, and check the homepage, a checklist, printing and the report form.
- Open `/health`. It should show `{"status": "ok"}`.
- Try signing in with a wrong password. You should see the usual error, and nothing else.
