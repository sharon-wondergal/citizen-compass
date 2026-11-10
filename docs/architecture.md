# Citizen Compass – Uganda: System Architecture

**Final documentation.** How the system is built, how its parts connect, and how to test it. The database is described separately in [database-design.md](database-design.md), with the diagram in [erd.mmd](erd.mmd).

## 1. Purpose

Citizen Compass turns official government information into a verified, structured checklist, so citizens know what to bring, what it costs, where to go and how long it takes before they travel. Its central rule is that **unconfirmed information is never presented as fact**.

## 2. Layers

```text
 Citizen browser          Administrator browser          Other applications
       │                          │                              │
       ▼                          ▼                              ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ ROUTES (Flask Blueprints): read the request, check it, choose a response │
├──────────────────────────────────────────────────────────────────────────┤
│ FORMS (Flask-WTF): validate everything a person types                    │
├──────────────────────────────────────────────────────────────────────────┤
│ LOGIC: every rule lives here once, shared by pages and the API           │
├──────────────────────────────────────────────────────────────────────────┤
│ MODELS (SQLAlchemy) → SQLite, with database rules as a final safeguard   │
└──────────────────────────────────────────────────────────────────────────┘
```

The web pages and the JSON API call the same logic. For example, `build_checklist()` decides whether a fee may be shown, so a page and the API can never disagree.

## 3. Blueprints

| Blueprint | Addresses | Who uses it |
|---|---|---|
| `main` | `/`, `/disclaimer`, `/privacy`, `/health` | Citizens, monitoring tools |
| `services` | `/services`, `/services/<slug>`, `/services/suggestions`, `/services/quick-answer` | Citizens |
| `directory` | `/institutions`, `/institutions/<slug>`, `/offices` | Citizens |
| `reports` | `/report`, `/report/thanks` | Citizens |
| `auth` | `/admin/login`, `/admin/logout` | Administrators |
| `admin` | Everything else under `/admin`, across `admin.py`, `admin_services.py`, `admin_directory.py`, `admin_verification.py` and `admin_reports.py` | Administrators |
| `api` | Everything under `/api/v1` | Other applications |

## 4. Logic modules

| Module | Responsibility |
|---|---|
| `checklist.py` | Builds the six-field checklist and applies the fee rule |
| `verification.py` | Works out what status citizens see, including "outdated" |
| `review.py` | The verification workflow, review queue and update history |
| `records.py` | Saving admin changes, resetting verification, audit comparisons |
| `search.py` | Search, filters, suggestions, spelling help and privacy-safe logging |
| `quick_answer.py` | The homepage answer card |
| `directory.py` | The institution directory and office finder |
| `auth.py` | Accounts, login, lockout and roles |
| `reports.py`, `report_review.py` | Citizen reports, their review, and privacy cleanup |
| `home.py`, `dashboard.py`, `insights.py`, `analytics.py` | Homepage data, dashboard, analytics and view counts |
| `api_data.py` | Turns records into JSON, without private details |

## 5. The trust model

1. Each service has five sections: overview, documents, fees, offices and processing.
2. Every section starts as **Pending verification**.
3. **Verified** needs an official source, a check date and a later review date. The database refuses it otherwise.
4. Nobody can verify their own change, and demonstration records can never be verified.
5. Any edit to a verified section returns it to pending.
6. Once the review date passes, a verified section shows as **Outdated – review required**.
7. A fee amount and its payment details reach citizens only once the fees section is verified.
8. A service shows its weakest section's status, so it never looks more certain than it is.

## 6. JSON API

Read-only. Every response is JSON, including errors, and unverified fees are never included.

| Method and address | Returns |
|---|---|
| `GET /api/v1` | The list of endpoints and a notice |
| `GET /api/v1/services` | Services. Filters: `q`, `category`, `institution`, `region`, `district`, `mode`, `status`, `page` |
| `GET /api/v1/services/<slug>` | One service |
| `GET /api/v1/services/<slug>/checklist` | The full checklist. Optional `situation` |
| `GET /api/v1/institutions` | Institutions. Filters: `q`, `type`, `page` |
| `GET /api/v1/institutions/<slug>` | One institution, with its services and offices |
| `GET /api/v1/offices` | Offices. Filters: `district`, `region`, `institution`, `service`, `page` |
| `GET /api/v1/categories` | Categories and their service counts |

Lists include `meta` with `page`, `pages`, `total` and `per_page`. Unknown parameters or values return `400` with an explanation, a missing record returns `404`, and more than 120 requests a minute returns `429`. Future authorised integrations, such as government data services, would connect through the logic layer without changing these addresses.

## 7. Security

| Protection | Where |
|---|---|
| Hashed passwords, lockout after 5 failures, one message for every failed login | `logic/auth.py` |
| Roles: editor, verifier, super administrator | `role_required()` in `logic/auth.py` |
| CSRF tokens on every form | Flask-WTF |
| SQL injection | SQLAlchemy always sends values as parameters |
| Cross-site scripting | Jinja2 escaping, a strict Content Security Policy, and scripts that never insert raw HTML |
| Clickjacking, file-type guessing, referrer leaks | Headers in `security.py` |
| Rate limits on search, login, reports and the API | Flask-Limiter |
| Secrets kept out of code | `.env`, which Git ignores |
| Private admin pages | `Cache-Control: no-store` and `X-Robots-Tag: noindex` |
| Minimal personal data | No citizen accounts. Search text has ID-like numbers removed. Report contacts are optional and blanked 90 days after closing |

## 8. Testing

The tests use a temporary in-memory database, so they never touch real data.

**In the PyCharm Terminal:**

```bash
python -m pytest
```

**With PyCharm's buttons:** right-click the `tests` folder and choose **Run 'Python tests in tests'**. If that option is missing, set the default test runner to pytest under **Settings → Tools → Python Integrated Tools**.

| Test file | Covers |
|---|---|
| `test_app_setup.py`, `test_security.py` | Startup safety, configuration and security headers |
| `test_models_schema.py`, `test_models_rules.py` | The database matches its design, and its rules hold |
| `test_home.py`, `test_search.py`, `test_quick_answer.py` | Homepage, search and the answer card |
| `test_checklist.py`, `test_verification_logic.py` | The checklist and status rules |
| `test_directory.py` | Institutions and the office finder |
| `test_auth.py`, `test_dashboard.py` | Login, roles and the dashboard |
| `test_admin_records.py`, `test_verification_workflow.py` | Managing records and verifying them |
| `test_prototype.py`, `test_report_review.py` | Citizen reports, their review, privacy cleanup and analytics |
| `test_real_services.py` | The real services stay sourced, pending and honest |
| `test_api.py` | The JSON API |

## 9. Known limitations

- **Search scale:** the verification filter runs in Python, which suits hundreds of services but not many thousands.
- **One server process:** rate limits are counted in memory unless `RATELIMIT_STORAGE_URI` is set.
- **English only:** text is in templates, ready for a translation library later.
- **No map:** offices store coordinates, but no map is shown yet.
- **Data upkeep:** the information is only as good as its last review, so someone must keep checking it.
