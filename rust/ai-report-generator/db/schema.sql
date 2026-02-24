CREATE TABLE indicators (
    id SERIAL PRIMARY KEY,
    code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(300) NOT NULL,
    frequency VARCHAR(20) NOT NULL,
    unit VARCHAR(100) NOT NULL,
    description TEXT
);

CREATE INDEX idx_indicators_code ON indicators(code);

CREATE TABLE data_points (
    id SERIAL PRIMARY KEY,
    indicator_id INTEGER NOT NULL REFERENCES indicators(id),
    observation_date DATE NOT NULL,
    value NUMERIC(20, 6) NOT NULL,
    UNIQUE(indicator_id, observation_date)
);

CREATE INDEX idx_data_points_indicator ON data_points(indicator_id);
CREATE INDEX idx_data_points_date ON data_points(observation_date);
CREATE INDEX idx_data_points_indicator_date ON data_points(indicator_id, observation_date DESC);

CREATE TABLE reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(500) NOT NULL,
    executive_summary TEXT NOT NULL,
    sections JSONB NOT NULL DEFAULT '[]',
    indicators_used TEXT[] NOT NULL,
    time_range_start DATE NOT NULL,
    time_range_end DATE NOT NULL,
    total_data_points INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    total_cost_usd NUMERIC(10, 6) DEFAULT 0,
    providers_used TEXT[] NOT NULL DEFAULT '{}',
    generation_duration_ms INTEGER DEFAULT 0,
    trace_id VARCHAR(32),
    status VARCHAR(20) NOT NULL DEFAULT 'completed',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_reports_status ON reports(status);
CREATE INDEX idx_reports_created ON reports(created_at DESC);
