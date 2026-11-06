# Citizen Compass – Uganda: Database Design

**Stage 2 deliverable.** This document explains the design. The exact definitions are in [schema_prototype.sql](schema_prototype.sql), the diagram is in [erd.mmd](erd.mmd), and [check_schema.py](check_schema.py) tests the rules.

## 1. Design principles

1. **Never claim more than we know.** Empty means "not confirmed". It never means zero, no or free.
2. **Every important fact can be traced to a source.**
3. **Verification is earned.** A record starts as pending, and the database refuses "verified" without evidence.
4. **Important rules live in the database too.** A bug in a form can't then save invalid data.
5. **Keep the structure as simple as the rules allow.** For example, update history reuses `audit_logs`.

## 2. How the six checklist fields map to tables

| Checklist field | Tables | Verification section |
|---|---|---|
| 1. Service information | `government_services`, `service_variants`, `service_steps` | `overview` |
| 2. Required documents | `required_documents` | `documents` |
| 3. Official fees | `service_fees` | `fees` |
| 4. Office locations | `service_offices`, `government_offices`, `districts`, `regions` | `offices` |
| 5. Processing time | `processing_information` | `processing` |
| 6. Sources and verification | `official_sources`, `verification_records` | Shows the other five |

## 3. Conventions

| Topic | Rule |
|---|---|
| Table names | Plural, in `snake_case` |
| Primary keys | Every table has an integer `id` |
| Money | Whole UGX in an integer column, never a decimal |
| Fixed choices | Text with a `CHECK` list, so database values are readable |
| Links | Must start with `http://` or `https://`, which blocks `javascript:` links |
| Page addresses | `slug` columns give stable, readable links such as `/services/example-service` |
| Removal | Public records are archived with `is_archived`, not deleted |

SQLite ignores foreign keys unless `PRAGMA foreign_keys = ON` is set on every connection. We'll set this in Stage 4 and test it.

## 4. Tables

`verification fields` below means `verification_status`, `last_verified_on`, `review_due_on` and `verified_by_id`.

### Locations

**regions:** `name` (unique).

**districts:** `name` (unique), `region_id`, `sub_region` (optional, such as Lango). Sub-region is plain text because nothing else depends on it. Offices get their region through their district, so the two can't disagree.

### Administrators

**admin_users**

| Column | Purpose |
|---|---|
| `full_name`, `email` (unique) | Identity. The email is the login name |
| `password_hash` | A one-way hash. The real password is never stored |
| `role` | `editor`, `verifier` or `super_admin` |
| `is_active` | Deactivates an account while keeping its history |
| `failed_login_count`, `locked_until` | Slows down password guessing |
| `last_login_at` | Security review |

### Institutions and sources

**government_institutions:** `name` and `slug` (unique), `acronym`, `institution_type`, `description`, `parent_id` (the parent ministry), `website`, `phone`, `email`, `headquarters`, `source_url`, verification fields, `is_demo`, `is_archived`.

**official_sources:** `institution_id` (the responsible agency), `title`, `url` (unique), `source_type`, `published_on`, `last_checked_on`. One source can support many services, so a single URSB charter is entered once.

> **Avoiding a circular link:** a source belongs to an institution. If an institution also pointed to a source, each table would depend on the other and neither could be created first. Institutions therefore store a plain `source_url`.

### Offices

**government_offices**

| Column | Purpose |
|---|---|
| `institution_id`, `district_id` | Who runs it and where it is |
| `name` | Unique within an institution |
| `office_type` | `headquarters`, `regional`, `district`, `service_centre` or `other` |
| `physical_address` | Empty until confirmed. The page says so instead of guessing |
| `phone`, `email`, `website`, `opening_hours` | Practical visit details |
| `latitude`, `longitude` | Map-ready. Both or neither, and empty until confirmed |
| `source_id`, verification fields, `is_demo`, `is_archived` | Trust and lifecycle |

### Services

**service_categories:** `name` and `slug` (unique), `description`, `icon`, `display_order`, `is_active`. Administrators can add more.

**government_services**

| Column | Purpose |
|---|---|
| `institution_id`, `category_id` | Responsible agency and category |
| `name` | Unique within an institution |
| `slug` | Unique, used in the shareable link |
| `summary`, `description` | Short and full explanation |
| `eligibility` | Who qualifies |
| `delivery_mode` | `online`, `physical` or `hybrid`. Empty until confirmed |
| `online_url` | Official portal, if any |
| `keywords` | Everyday search words and alternative names |
| `is_demo`, `is_archived`, `created_by_id` | Lifecycle |

**service_variants:** `service_id`, `name` (unique within a service), `description`, `is_default`, `display_order`. A variant is the citizen's *situation*, such as new, renewal or lost.

**required_documents**

| Column | Purpose |
|---|---|
| `service_id`, `variant_id`, `source_id` | Links. No variant means it applies to all cases |
| `name`, `is_mandatory` | The checklist item |
| `original_required`, `certified_copy_accepted` | Yes, no, or empty for "not confirmed" |
| `photocopies` | Number required, or empty for "not confirmed" |
| `max_age_days` | How recent the document must be |
| `instructions`, `display_order` | Extra guidance and sort order |

**service_fees**

| Column | Purpose |
|---|---|
| `service_id`, `variant_id`, `source_id` | Links |
| `fee_name`, `fee_kind` | `official` or `other_charge` |
| `service_speed` | `ordinary`, `express` or `not_applicable` |
| `amount_ugx` | **Empty means unconfirmed. 0 means confirmed free** |
| `is_mandatory` | Whether every applicant must pay it |
| `payment_method`, `payment_instructions` | How to pay |
| `effective_from` | Date the amount applies from |
| `display_order` | Sort order |

**processing_information**

| Column | Purpose |
|---|---|
| `service_id`, `variant_id`, `source_id` | Links |
| `service_speed` | Ordinary and express can have separate rows |
| `min_working_days`, `max_working_days` | Range. Minimum can't exceed maximum |
| `duration_note` | Wording that doesn't fit a number |
| `starts_after` | `submission`, `payment`, `approval` or `unknown` |
| `basis` | `official_standard`, `estimate` or `unverified` |
| `delay_factors` | What can slow it down |

**service_steps:** `service_id`, `variant_id`, `source_id`, `step_number`, `stage` (`before_visit`, `at_office` or `after_visit`), `title`, `instructions`, `action_url`.

**service_offices:** `service_id`, `office_id` (a pair can appear once), `source_id`, `availability_note`, `verification_status`, `last_verified_on`. This is a many-to-many link with its own evidence, because "this office offers this service" is a claim that needs proof.

**verification_records**

| Column | Purpose |
|---|---|
| `service_id`, `section` | One row per section, per service |
| `status` | `pending`, `verified`, `outdated` or `unavailable` |
| `source_id` | Evidence for the section |
| `last_checked_on`, `review_due_on` | Shown to citizens |
| `verified_by_id`, `last_edited_by_id` | Enforces separate approval |
| `notes` | Internal verifier notes |

### Citizen input and analytics

**citizen_reports**

| Column | Purpose |
|---|---|
| `reference_code` | Unique code the citizen can quote |
| `service_id`, `service_name` | The name is kept if the service is later removed |
| `problem_type` | One of the six reportable problems |
| `description` | 10 to 2,000 characters |
| `contact_info` | Optional |
| `status` | `new`, `investigating`, `resolved` or `dismissed` |
| `action_taken`, `resolved_by_id`, `resolved_at` | Required to close a report |
| `submitted_at` | Submission date |

**search_logs:** `query_text` (cleaned, 100 characters at most), `results_count`, `top_service_id`, `top_institution_id`, `searched_at`. It stores no IP address or user identifier.

**daily_views:** `view_date`, `view_count`, and either `service_id` or `institution_id`. It stores totals only, not individual visits.

**audit_logs:** `admin_user_id`, `action`, `table_name`, `record_id`, `record_label`, `old_values`, `new_values` (JSON text), `created_at`. The application only ever adds rows here.

## 5. Relationships

| Relationship | Type | If the parent is deleted |
|---|---|---|
| Region → districts | One to many | Blocked |
| District → offices | One to many | Blocked |
| Institution → child institutions | One to many (self-link) | Child stays, link cleared |
| Institution → offices, services, sources | One to many | Blocked |
| Category → services | One to many | Blocked |
| Service → variants, documents, fees, processing, steps, verification records | One to many | Deleted with the service |
| Variant → documents, fees, processing, steps | One to many, optional | Deleted with the variant |
| Service ↔ office | Many to many through `service_offices` | Link removed |
| Source → anything citing it | One to many, optional | Blocked, so citations aren't lost |
| Service → citizen reports, search logs | One to many, optional | Report or log stays, link cleared |
| Admin → verification, reports, audit logs | One to many | Blocked. Accounts are deactivated instead |

## 6. Verification rules

**Status shown to citizens**

| Stored value | Label |
|---|---|
| `verified` | Verified |
| `pending` | Pending verification |
| `outdated` | Outdated – review required |
| `unavailable` | Information unavailable |

**Rules enforced by the database, and tested**
- "Verified" requires a source, a check date, a review date and a verifier.
- The last editor of a section can't be its verifier.
- A demonstration office or institution can never be verified.
- A verified service-office link requires a source and date.

**Rules enforced by the logic layer, built and tested in later stages**
- **New records:** every new service gets five `pending` verification records.
- **Editing resets verification:** changing anything in a verified section sets it back to `pending`. Otherwise a fee could change while still showing "Verified".
- **Outdated is calculated:** a verified record past its `review_due_on` displays as outdated. No scheduled job is needed.
- **Overall status:** a service shows its weakest section. The order from worst is unavailable, outdated, pending, verified.
- **Demonstration services:** a service marked `is_demo` can't have a section verified. This spans two tables, so a simple `CHECK` can't enforce it.
- **Matching variants:** a row's variant must belong to the same service.
- **Review period:** the review date defaults to six months after checking, and the verifier can change it.
- **Fee display:** an amount is shown only when the fees section is `verified` or `outdated`, and outdated amounts carry a warning. Otherwise the page shows "Official fee not yet verified. Please confirm with the responsible agency."
- **Office display:** an office appears as confirmed only if its service link is verified. Pending links are labelled.
- **Verifier names:** these stay in the admin area. Citizens see the date, source and status.

```text
          new or edited                   verifier approves
 (start) ───────────────▶ pending ───────────────────────▶ verified
                            ▲  ▲                              │
                            │  └──── any edit ────────────────┤
                            │                                 │ review date passes,
                            └─── re-checked, not confirmed    ▼ or marked by hand
                                 ◀──────────────────────── outdated

 No official information found: any status ───▶ unavailable
```

## 7. Privacy rules

| Data | Rule |
|---|---|
| Citizen accounts | None |
| Ticked checklist items | Stay in the citizen's browser |
| National ID numbers, payment details | Never requested |
| Search text | Long number and ID-like text is removed before saving |
| IP addresses | Not stored in these tables |
| Report contact details | Optional, and blanked 90 days after a report closes |
| Search logs | Deleted after 12 months, because totals are enough for long-term analytics |

The 90-day and 12-month periods are proposals to review before any public launch.

## 8. Analytics sources

| Insight | Comes from |
|---|---|
| Most searched services | `search_logs.top_service_id` |
| Services citizens couldn't find | `search_logs` where `results_count` is 0 |
| Most viewed services | `daily_views.service_id` |
| Most requested institutions | `daily_views.institution_id`, `search_logs.top_institution_id` |
| Most reported information | `citizen_reports` by service and problem type |
| Outdated services | `verification_records` compared with today's date |
| Common preparation challenges | Report types combined with failed searches |

## 9. Known limitations

- **Duplicate rows for all-variant items:** SQLite treats empty values as different in unique rules, so two identical documents with no variant could exist. The admin form will check for this.
- **Evidence for service-office links:** these have no review date of their own. The `offices` section record covers the review cycle.
- **Institution sources:** these are plain URLs, so they aren't listed with `official_sources`.
- **Translations:** there are no language tables yet. Text columns can later move to translation tables without changing the relationships.
