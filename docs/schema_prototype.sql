-- Citizen Compass - Uganda: Stage 2 schema prototype
--
-- This file tests the database DESIGN. It is not used by the running app.
-- In Stage 5 the same tables are written as SQLAlchemy models.
--
-- Status values used across the design:
--   pending      = Pending verification
--   verified     = Verified
--   outdated     = Outdated - review required
--   unavailable  = Information unavailable

-- ---------- Locations ----------

CREATE TABLE regions (
    id    INTEGER PRIMARY KEY,
    name  VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE districts (
    id          INTEGER PRIMARY KEY,
    name        VARCHAR(80) NOT NULL UNIQUE,
    region_id   INTEGER NOT NULL REFERENCES regions(id) ON DELETE RESTRICT,
    sub_region  VARCHAR(80)
);
CREATE INDEX ix_districts_region ON districts(region_id);

-- ---------- Administrators ----------

CREATE TABLE admin_users (
    id                  INTEGER PRIMARY KEY,
    full_name           VARCHAR(120) NOT NULL,
    email               VARCHAR(255) NOT NULL UNIQUE,
    password_hash       VARCHAR(255) NOT NULL,
    role                VARCHAR(20) NOT NULL DEFAULT 'editor'
                        CHECK (role IN ('editor', 'verifier', 'super_admin')),
    is_active           BOOLEAN NOT NULL DEFAULT 1,
    failed_login_count  INTEGER NOT NULL DEFAULT 0 CHECK (failed_login_count >= 0),
    locked_until        DATETIME,
    last_login_at       DATETIME,
    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ---------- Institutions and sources ----------

CREATE TABLE government_institutions (
    id                   INTEGER PRIMARY KEY,
    name                 VARCHAR(200) NOT NULL UNIQUE,
    slug                 VARCHAR(220) NOT NULL UNIQUE,
    acronym              VARCHAR(20),
    institution_type     VARCHAR(20) NOT NULL DEFAULT 'agency'
                         CHECK (institution_type IN
                               ('ministry', 'department', 'agency', 'local_government', 'other')),
    description          TEXT,
    parent_id            INTEGER REFERENCES government_institutions(id) ON DELETE SET NULL,
    website              VARCHAR(500)
                         CHECK (website IS NULL OR website LIKE 'http://%' OR website LIKE 'https://%'),
    phone                VARCHAR(50),
    email                VARCHAR(255),
    headquarters         VARCHAR(300),
    -- A plain URL, not a link to official_sources. See "circular link" in the design document.
    source_url           VARCHAR(500)
                         CHECK (source_url IS NULL OR source_url LIKE 'http://%' OR source_url LIKE 'https://%'),
    verification_status  VARCHAR(20) NOT NULL DEFAULT 'pending'
                         CHECK (verification_status IN ('pending', 'verified', 'outdated', 'unavailable')),
    last_verified_on     DATE,
    review_due_on        DATE,
    verified_by_id       INTEGER REFERENCES admin_users(id) ON DELETE RESTRICT,
    is_demo              BOOLEAN NOT NULL DEFAULT 0,
    is_archived          BOOLEAN NOT NULL DEFAULT 0,
    created_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (verification_status <> 'verified' OR
           (source_url IS NOT NULL AND last_verified_on IS NOT NULL
            AND review_due_on IS NOT NULL AND verified_by_id IS NOT NULL)),
    CHECK (NOT (is_demo = 1 AND verification_status = 'verified'))
);
CREATE INDEX ix_institutions_parent ON government_institutions(parent_id);
CREATE INDEX ix_institutions_acronym ON government_institutions(acronym);

CREATE TABLE official_sources (
    id               INTEGER PRIMARY KEY,
    institution_id   INTEGER NOT NULL REFERENCES government_institutions(id) ON DELETE RESTRICT,
    title            VARCHAR(300) NOT NULL,
    url              VARCHAR(500) NOT NULL UNIQUE
                     CHECK (url LIKE 'http://%' OR url LIKE 'https://%'),
    source_type      VARCHAR(20) NOT NULL DEFAULT 'web_page'
                     CHECK (source_type IN ('web_page', 'pdf', 'client_charter', 'gazette', 'other')),
    published_on     DATE,
    last_checked_on  DATE,
    created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ix_sources_institution ON official_sources(institution_id);

-- ---------- Offices ----------

CREATE TABLE government_offices (
    id                   INTEGER PRIMARY KEY,
    institution_id       INTEGER NOT NULL REFERENCES government_institutions(id) ON DELETE RESTRICT,
    district_id          INTEGER NOT NULL REFERENCES districts(id) ON DELETE RESTRICT,
    name                 VARCHAR(200) NOT NULL,
    office_type          VARCHAR(20) NOT NULL DEFAULT 'district'
                         CHECK (office_type IN
                               ('headquarters', 'regional', 'district', 'service_centre', 'other')),
    physical_address     VARCHAR(300),
    phone                VARCHAR(50),
    email                VARCHAR(255),
    website              VARCHAR(500)
                         CHECK (website IS NULL OR website LIKE 'http://%' OR website LIKE 'https://%'),
    opening_hours        VARCHAR(200),
    latitude             REAL CHECK (latitude IS NULL OR latitude BETWEEN -90 AND 90),
    longitude            REAL CHECK (longitude IS NULL OR longitude BETWEEN -180 AND 180),
    source_id            INTEGER REFERENCES official_sources(id) ON DELETE RESTRICT,
    verification_status  VARCHAR(20) NOT NULL DEFAULT 'pending'
                         CHECK (verification_status IN ('pending', 'verified', 'outdated', 'unavailable')),
    last_verified_on     DATE,
    review_due_on        DATE,
    verified_by_id       INTEGER REFERENCES admin_users(id) ON DELETE RESTRICT,
    is_demo              BOOLEAN NOT NULL DEFAULT 0,
    is_archived          BOOLEAN NOT NULL DEFAULT 0,
    created_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (institution_id, name),
    CHECK ((latitude IS NULL) = (longitude IS NULL)),
    CHECK (verification_status <> 'verified' OR
           (source_id IS NOT NULL AND last_verified_on IS NOT NULL
            AND review_due_on IS NOT NULL AND verified_by_id IS NOT NULL)),
    CHECK (NOT (is_demo = 1 AND verification_status = 'verified'))
);
CREATE INDEX ix_offices_district ON government_offices(district_id);

-- ---------- Services ----------

CREATE TABLE service_categories (
    id             INTEGER PRIMARY KEY,
    name           VARCHAR(120) NOT NULL UNIQUE,
    slug           VARCHAR(140) NOT NULL UNIQUE,
    description    TEXT,
    icon           VARCHAR(50),
    display_order  INTEGER NOT NULL DEFAULT 0,
    is_active      BOOLEAN NOT NULL DEFAULT 1
);

CREATE TABLE government_services (
    id              INTEGER PRIMARY KEY,
    institution_id  INTEGER NOT NULL REFERENCES government_institutions(id) ON DELETE RESTRICT,
    category_id     INTEGER NOT NULL REFERENCES service_categories(id) ON DELETE RESTRICT,
    name            VARCHAR(200) NOT NULL,
    slug            VARCHAR(220) NOT NULL UNIQUE,
    summary         VARCHAR(300) NOT NULL,
    description     TEXT,
    eligibility     TEXT,
    delivery_mode   VARCHAR(10) CHECK (delivery_mode IS NULL OR
                                       delivery_mode IN ('online', 'physical', 'hybrid')),
    online_url      VARCHAR(500)
                    CHECK (online_url IS NULL OR online_url LIKE 'http://%' OR online_url LIKE 'https://%'),
    keywords        VARCHAR(500),
    is_demo         BOOLEAN NOT NULL DEFAULT 0,
    is_archived     BOOLEAN NOT NULL DEFAULT 0,
    created_by_id   INTEGER REFERENCES admin_users(id) ON DELETE RESTRICT,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (institution_id, name)
);
CREATE INDEX ix_services_category ON government_services(category_id);

-- The citizen's situation: new, renewal, lost and so on.
-- Ordinary and express are NOT variants. They are the service_speed column below.
CREATE TABLE service_variants (
    id             INTEGER PRIMARY KEY,
    service_id     INTEGER NOT NULL REFERENCES government_services(id) ON DELETE CASCADE,
    name           VARCHAR(120) NOT NULL,
    description    TEXT,
    is_default     BOOLEAN NOT NULL DEFAULT 0,
    display_order  INTEGER NOT NULL DEFAULT 0,
    UNIQUE (service_id, name)
);

-- In the next four tables, variant_id NULL means "applies to every variant".
-- In required_documents, NULL in a yes/no column means "not yet confirmed".

CREATE TABLE required_documents (
    id                       INTEGER PRIMARY KEY,
    service_id               INTEGER NOT NULL REFERENCES government_services(id) ON DELETE CASCADE,
    variant_id               INTEGER REFERENCES service_variants(id) ON DELETE CASCADE,
    source_id                INTEGER REFERENCES official_sources(id) ON DELETE RESTRICT,
    name                     VARCHAR(200) NOT NULL,
    is_mandatory             BOOLEAN NOT NULL DEFAULT 1,
    original_required        BOOLEAN,
    photocopies              INTEGER CHECK (photocopies IS NULL OR photocopies >= 0),
    certified_copy_accepted  BOOLEAN,
    max_age_days             INTEGER CHECK (max_age_days IS NULL OR max_age_days > 0),
    instructions             TEXT,
    display_order            INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX ix_documents_service ON required_documents(service_id);

CREATE TABLE service_fees (
    id                    INTEGER PRIMARY KEY,
    service_id            INTEGER NOT NULL REFERENCES government_services(id) ON DELETE CASCADE,
    variant_id            INTEGER REFERENCES service_variants(id) ON DELETE CASCADE,
    source_id             INTEGER REFERENCES official_sources(id) ON DELETE RESTRICT,
    fee_name              VARCHAR(200) NOT NULL,
    fee_kind              VARCHAR(20) NOT NULL DEFAULT 'official'
                          CHECK (fee_kind IN ('official', 'other_charge')),
    service_speed         VARCHAR(20) NOT NULL DEFAULT 'not_applicable'
                          CHECK (service_speed IN ('ordinary', 'express', 'not_applicable')),
    -- Whole shillings. NULL = not confirmed. 0 = confirmed free.
    amount_ugx            INTEGER CHECK (amount_ugx IS NULL OR amount_ugx >= 0),
    is_mandatory          BOOLEAN NOT NULL DEFAULT 1,
    payment_method        VARCHAR(200),
    payment_instructions  TEXT,
    effective_from        DATE,
    display_order         INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX ix_fees_service ON service_fees(service_id);

CREATE TABLE processing_information (
    id                INTEGER PRIMARY KEY,
    service_id        INTEGER NOT NULL REFERENCES government_services(id) ON DELETE CASCADE,
    variant_id        INTEGER REFERENCES service_variants(id) ON DELETE CASCADE,
    source_id         INTEGER REFERENCES official_sources(id) ON DELETE RESTRICT,
    service_speed     VARCHAR(20) NOT NULL DEFAULT 'not_applicable'
                      CHECK (service_speed IN ('ordinary', 'express', 'not_applicable')),
    min_working_days  INTEGER CHECK (min_working_days IS NULL OR min_working_days >= 0),
    max_working_days  INTEGER CHECK (max_working_days IS NULL OR max_working_days >= 0),
    duration_note     VARCHAR(200),
    starts_after      VARCHAR(20) NOT NULL DEFAULT 'unknown'
                      CHECK (starts_after IN ('submission', 'payment', 'approval', 'unknown')),
    basis             VARCHAR(20) NOT NULL DEFAULT 'unverified'
                      CHECK (basis IN ('official_standard', 'estimate', 'unverified')),
    delay_factors     TEXT,
    CHECK (min_working_days IS NULL OR max_working_days IS NULL
           OR min_working_days <= max_working_days)
);
CREATE INDEX ix_processing_service ON processing_information(service_id);

CREATE TABLE service_steps (
    id            INTEGER PRIMARY KEY,
    service_id    INTEGER NOT NULL REFERENCES government_services(id) ON DELETE CASCADE,
    variant_id    INTEGER REFERENCES service_variants(id) ON DELETE CASCADE,
    source_id     INTEGER REFERENCES official_sources(id) ON DELETE RESTRICT,
    step_number   INTEGER NOT NULL CHECK (step_number > 0),
    stage         VARCHAR(20) NOT NULL DEFAULT 'before_visit'
                  CHECK (stage IN ('before_visit', 'at_office', 'after_visit')),
    title         VARCHAR(200) NOT NULL,
    instructions  TEXT,
    action_url    VARCHAR(500)
                  CHECK (action_url IS NULL OR action_url LIKE 'http://%' OR action_url LIKE 'https://%')
);
CREATE INDEX ix_steps_service ON service_steps(service_id);

-- "This office provides this service." The claim itself needs evidence.
CREATE TABLE service_offices (
    id                   INTEGER PRIMARY KEY,
    service_id           INTEGER NOT NULL REFERENCES government_services(id) ON DELETE CASCADE,
    office_id            INTEGER NOT NULL REFERENCES government_offices(id) ON DELETE CASCADE,
    source_id            INTEGER REFERENCES official_sources(id) ON DELETE RESTRICT,
    availability_note    VARCHAR(300),
    verification_status  VARCHAR(20) NOT NULL DEFAULT 'pending'
                         CHECK (verification_status IN ('pending', 'verified', 'outdated', 'unavailable')),
    last_verified_on     DATE,
    UNIQUE (service_id, office_id),
    CHECK (verification_status <> 'verified' OR
           (source_id IS NOT NULL AND last_verified_on IS NOT NULL))
);
CREATE INDEX ix_service_offices_office ON service_offices(office_id);

-- One row per section of each service. This is the heart of the trust model.
CREATE TABLE verification_records (
    id                 INTEGER PRIMARY KEY,
    service_id         INTEGER NOT NULL REFERENCES government_services(id) ON DELETE CASCADE,
    section            VARCHAR(20) NOT NULL
                       CHECK (section IN ('overview', 'documents', 'fees', 'offices', 'processing')),
    status             VARCHAR(20) NOT NULL DEFAULT 'pending'
                       CHECK (status IN ('pending', 'verified', 'outdated', 'unavailable')),
    source_id          INTEGER REFERENCES official_sources(id) ON DELETE RESTRICT,
    last_checked_on    DATE,
    review_due_on      DATE,
    verified_by_id     INTEGER REFERENCES admin_users(id) ON DELETE RESTRICT,
    last_edited_by_id  INTEGER REFERENCES admin_users(id) ON DELETE RESTRICT,
    notes              TEXT,
    updated_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (service_id, section),
    CHECK (status <> 'verified' OR
           (source_id IS NOT NULL AND last_checked_on IS NOT NULL
            AND review_due_on IS NOT NULL AND verified_by_id IS NOT NULL)),
    -- Separate approval: the last editor cannot verify their own change.
    CHECK (status <> 'verified' OR last_edited_by_id IS NULL
           OR verified_by_id <> last_edited_by_id)
);
CREATE INDEX ix_verification_review ON verification_records(status, review_due_on);

-- ---------- Citizen input and analytics ----------

CREATE TABLE citizen_reports (
    id              INTEGER PRIMARY KEY,
    reference_code  VARCHAR(20) NOT NULL UNIQUE,
    service_id      INTEGER REFERENCES government_services(id) ON DELETE SET NULL,
    service_name    VARCHAR(200) NOT NULL,
    problem_type    VARCHAR(30) NOT NULL
                    CHECK (problem_type IN ('incorrect_fee', 'missing_document', 'incorrect_office',
                                            'outdated_processing', 'broken_link', 'other')),
    description     VARCHAR(2000) NOT NULL CHECK (length(description) BETWEEN 10 AND 2000),
    contact_info    VARCHAR(200),
    status          VARCHAR(20) NOT NULL DEFAULT 'new'
                    CHECK (status IN ('new', 'investigating', 'resolved', 'dismissed')),
    action_taken    TEXT,
    resolved_by_id  INTEGER REFERENCES admin_users(id) ON DELETE RESTRICT,
    resolved_at     DATETIME,
    submitted_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (status NOT IN ('resolved', 'dismissed') OR
           (action_taken IS NOT NULL AND resolved_by_id IS NOT NULL AND resolved_at IS NOT NULL))
);
CREATE INDEX ix_reports_status ON citizen_reports(status);

CREATE TABLE search_logs (
    id                  INTEGER PRIMARY KEY,
    query_text          VARCHAR(100) NOT NULL,
    results_count       INTEGER NOT NULL CHECK (results_count >= 0),
    top_service_id      INTEGER REFERENCES government_services(id) ON DELETE SET NULL,
    top_institution_id  INTEGER REFERENCES government_institutions(id) ON DELETE SET NULL,
    searched_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ix_search_logs_date ON search_logs(searched_at);

CREATE TABLE daily_views (
    id              INTEGER PRIMARY KEY,
    view_date       DATE NOT NULL,
    service_id      INTEGER REFERENCES government_services(id) ON DELETE CASCADE,
    institution_id  INTEGER REFERENCES government_institutions(id) ON DELETE CASCADE,
    view_count      INTEGER NOT NULL DEFAULT 0 CHECK (view_count >= 0),
    UNIQUE (view_date, service_id),
    UNIQUE (view_date, institution_id),
    -- Each row counts exactly one thing.
    CHECK ((service_id IS NULL) <> (institution_id IS NULL))
);

CREATE TABLE audit_logs (
    id             INTEGER PRIMARY KEY,
    admin_user_id  INTEGER REFERENCES admin_users(id) ON DELETE RESTRICT,
    action         VARCHAR(20) NOT NULL
                   CHECK (action IN ('create', 'update', 'delete', 'archive', 'restore',
                                     'verify', 'status_change', 'resolve_report', 'login')),
    table_name     VARCHAR(50) NOT NULL,
    record_id      INTEGER,
    record_label   VARCHAR(200),
    old_values     TEXT,
    new_values     TEXT,
    created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ix_audit_record ON audit_logs(table_name, record_id);
CREATE INDEX ix_audit_date ON audit_logs(created_at);
