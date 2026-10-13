-- Results-to-Thesis Copilot, Phase 1 schema (procedure Section 4).
-- Values are stored as TEXT holding exact decimals, never REAL.
-- NULL value means missing: never zero-filled.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS documents (
    id               INTEGER PRIMARY KEY,
    company          TEXT NOT NULL,
    quarter          TEXT NOT NULL,                 -- e.g. Q1FY27
    type             TEXT NOT NULL CHECK (type IN ('xbrl', 'results_release', 'presentation', 'transcript', 'press_release', 'analyst_model')),
    file_path        TEXT NOT NULL,
    sha256           TEXT NOT NULL,
    source_url       TEXT,
    publication_date TEXT,                          -- ISO date
    ingested_at      TEXT NOT NULL,                 -- ISO timestamp, UTC
    UNIQUE (company, quarter, type, sha256)
);

CREATE TABLE IF NOT EXISTS pages (                  -- page-level text (Step 4)
    document_id INTEGER NOT NULL REFERENCES documents(id),
    page        INTEGER NOT NULL,                   -- as shown in the viewer, from 1
    text        TEXT NOT NULL,
    scanned     INTEGER NOT NULL DEFAULT 0 CHECK (scanned IN (0, 1)),
    PRIMARY KEY (document_id, page)
);

CREATE TABLE IF NOT EXISTS figures (
    id             INTEGER PRIMARY KEY,
    company        TEXT NOT NULL,
    quarter        TEXT NOT NULL,                   -- report quarter this figure belongs to
    metric         TEXT NOT NULL,                   -- metrics.yaml id
    period         TEXT NOT NULL,                   -- quarter the value describes, e.g. Q4FY26
    basis          TEXT NOT NULL CHECK (basis IN ('consolidated', 'standalone')),
    segment        TEXT,                            -- NULL for company-level figures
    value          TEXT,                            -- exact decimal, normalised (₹ crore for money); NULL = missing
    unit           TEXT NOT NULL,
    original_value TEXT,                            -- as printed in the source
    original_unit  TEXT,                            -- lakh / million / crore / ...
    document_id    INTEGER REFERENCES documents(id),
    source_ref     TEXT,                            -- page number, or XBRL context id
    source_detail  TEXT,                            -- XBRL element, or PDF row label + column header
    method         TEXT NOT NULL CHECK (method IN ('xbrl', 'pdf', 'derived', 'manual')),
    derivation     TEXT,                            -- JSON: formula and input figure ids, for derived
    -- extracted = not yet through the Step 8 checks
    status         TEXT NOT NULL CHECK (status IN ('extracted', 'verified', 'low_confidence', 'missing', 'manually_verified')),
    note           TEXT,                            -- why a figure is missing or low confidence
    supersedes     INTEGER REFERENCES figures(id),  -- analyst correction points at the original
    reason         TEXT,                            -- mandatory for corrections
    created_at     TEXT NOT NULL,
    CHECK (supersedes IS NULL OR reason IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS figures_lookup ON figures (company, quarter, metric, period);

CREATE TABLE IF NOT EXISTS estimates (
    id            INTEGER PRIMARY KEY,
    company       TEXT NOT NULL,
    quarter       TEXT NOT NULL,
    metric        TEXT NOT NULL,
    segment       TEXT,                             -- NULL for company-level estimates
    value         TEXT,                             -- exact decimal; NULL = no cached value
    unit          TEXT NOT NULL,
    sheet         TEXT NOT NULL,
    cell          TEXT NOT NULL,
    estimate_date TEXT,
    is_sample     INTEGER NOT NULL DEFAULT 1 CHECK (is_sample IN (0, 1)),
    document_id   INTEGER REFERENCES documents(id)
);

CREATE TABLE IF NOT EXISTS comparisons (
    id          INTEGER PRIMARY KEY,
    figure_id   INTEGER NOT NULL REFERENCES figures(id),
    comparator  TEXT NOT NULL CHECK (comparator IN ('prior', 'year_ago', 'estimate')),
    comparator_figure_id   INTEGER REFERENCES figures(id),
    comparator_estimate_id INTEGER REFERENCES estimates(id),
    change      TEXT,                               -- absolute change, exact decimal
    change_pct  TEXT,                               -- NULL when base is zero/negative (n.m.)
    change_bps  TEXT,                               -- margins and rate KPIs
    not_meaningful INTEGER NOT NULL DEFAULT 0 CHECK (not_meaningful IN (0, 1)),
    severity    TEXT CHECK (severity IN ('low', 'medium', 'high')),
    gap_reason  TEXT,                               -- set instead of a change when comparator is missing
    UNIQUE (figure_id, comparator)
);

CREATE TABLE IF NOT EXISTS statements (
    id           INTEGER PRIMARY KEY,
    company      TEXT NOT NULL,
    quarter      TEXT NOT NULL,
    type         TEXT NOT NULL CHECK (type IN ('guidance', 'flag', 'explanation')),
    topic        TEXT,
    quote        TEXT NOT NULL,                     -- exact quote from the source
    document_id  INTEGER NOT NULL REFERENCES documents(id),
    page         INTEGER NOT NULL,
    speaker      TEXT,
    rule_matched TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reviews (
    id        INTEGER PRIMARY KEY,
    report    TEXT NOT NULL,                        -- e.g. MM_Q1FY27
    item      TEXT NOT NULL,                        -- e.g. figure:12, statement:4, report
    reviewer  TEXT NOT NULL,
    action    TEXT NOT NULL CHECK (action IN ('approve', 'reject', 'comment', 'correct')),
    comment   TEXT,
    old_value TEXT,
    new_value TEXT,
    time      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id      INTEGER PRIMARY KEY,
    time    TEXT NOT NULL,
    user    TEXT NOT NULL,
    action  TEXT NOT NULL,
    item    TEXT,
    details TEXT                                    -- JSON
);

-- The audit log is append-only.
CREATE TRIGGER IF NOT EXISTS audit_log_no_update BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_log_no_delete BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
