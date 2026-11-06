# Citizen Compass – Uganda

**Know Before You Go.**

Citizen Compass is a government service preparation platform. It helps citizens check what documents they need, what a service costs, where to go and how long it takes, before they travel to a government office.

> Citizen Compass is an independent university project. It is not a government website, and it does not process applications or payments.

## Project status

Under development, stage by stage. The homepage works, but search and the service directory aren't built yet.

| Stage | Topic | Status |
|---|---|---|
| 1 | Requirements and architecture | Done |
| 2 | Database design and ERD | Done: see [docs/database-design.md](docs/database-design.md) |
| 3 | PyCharm project and virtual environment | Done |
| 4 | Flask configuration | Done |
| 5 | Database models and relationships | Done |
| 6 | Homepage and navigation | Done |
| 7 | Service directory and search | Next |

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
