CREATE TABLE companies (
    cik     bigint PRIMARY KEY,
    name    text NOT NULL
);

CREATE TABLE tickers (
    ticker  text PRIMARY KEY,
    cik     bigint NOT NULL REFERENCES companies (cik)
);

CREATE TABLE facts (
    cik           bigint NOT NULL REFERENCES companies (cik),
    taxonomy      text NOT NULL,
    concept       text NOT NULL,
    unit          text NOT NULL,
    period_start  date,
    period_end    date NOT NULL,
    value         numeric NOT NULL,
    filing_fy     integer,
    filing_fp     text,
    form          text NOT NULL,
    filed         date NOT NULL,
    accession     text NOT NULL,
    frame         text,
    CONSTRAINT facts_identity UNIQUE NULLS NOT DISTINCT
        (cik, taxonomy, concept, unit, period_start, period_end, accession)
);

CREATE INDEX facts_lookup ON facts (cik, concept, unit, period_end);

CREATE TABLE fact_loads (
    cik        bigint PRIMARY KEY REFERENCES companies (cik),
    loaded_at  timestamptz NOT NULL DEFAULT now(),
    source     text NOT NULL CHECK (source IN ('cache', 'sec')),
    row_count  integer NOT NULL
);
