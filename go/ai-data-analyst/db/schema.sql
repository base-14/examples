CREATE TABLE IF NOT EXISTS countries (
  id SERIAL PRIMARY KEY,
  name VARCHAR(200) NOT NULL,
  code VARCHAR(3) NOT NULL UNIQUE,
  region VARCHAR(100) NOT NULL,
  income_group VARCHAR(50) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_countries_code ON countries(code);
CREATE INDEX IF NOT EXISTS idx_countries_region ON countries(region);

CREATE TABLE IF NOT EXISTS indicators (
  id SERIAL PRIMARY KEY,
  name VARCHAR(300) NOT NULL,
  code VARCHAR(50) NOT NULL UNIQUE,
  category VARCHAR(100) NOT NULL,
  unit VARCHAR(100) NOT NULL,
  description TEXT
);

CREATE INDEX IF NOT EXISTS idx_indicators_code ON indicators(code);
CREATE INDEX IF NOT EXISTS idx_indicators_category ON indicators(category);

CREATE TABLE IF NOT EXISTS indicator_values (
  id SERIAL PRIMARY KEY,
  country_id INTEGER NOT NULL REFERENCES countries(id),
  indicator_id INTEGER NOT NULL REFERENCES indicators(id),
  year INTEGER NOT NULL,
  value NUMERIC(20, 6),
  UNIQUE(country_id, indicator_id, year)
);

CREATE INDEX IF NOT EXISTS idx_values_country ON indicator_values(country_id);
CREATE INDEX IF NOT EXISTS idx_values_indicator ON indicator_values(indicator_id);
CREATE INDEX IF NOT EXISTS idx_values_year ON indicator_values(year);
CREATE INDEX IF NOT EXISTS idx_values_country_indicator
  ON indicator_values(country_id, indicator_id, year DESC);

CREATE TABLE IF NOT EXISTS query_history (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  question TEXT NOT NULL,
  question_type VARCHAR(50),
  generated_sql TEXT NOT NULL,
  confidence NUMERIC(3, 2),
  row_count INTEGER,
  execution_ms INTEGER,
  total_tokens INTEGER,
  total_cost_usd NUMERIC(10, 6),
  explanation TEXT,
  trace_id VARCHAR(32),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_history_created ON query_history(created_at DESC);
