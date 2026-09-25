-- The KYC app has its own database on the Postgres instance Temporal uses.
CREATE DATABASE kyc;

\connect kyc

-- screen_sanctions uses pg_trgm's similarity() for near-match screening.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE sanctions (
    id SERIAL PRIMARY KEY,
    full_name TEXT NOT NULL,
    country TEXT,
    listed_on DATE NOT NULL DEFAULT CURRENT_DATE
);

CREATE INDEX idx_sanctions_full_name_trgm ON sanctions USING gin (full_name gin_trgm_ops);

-- `consumed` lets `PostgresFaultRegistry.consume_once` fire a fault once per case, atomically,
-- even when two activity attempts race for it.
CREATE TABLE case_faults (
    case_id TEXT NOT NULL,
    fault TEXT NOT NULL,
    consumed BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (case_id, fault)
);
