-- AI Contract Analyzer — PostgreSQL Schema
-- Requires: PostgreSQL 18 + pgvector extension

CREATE EXTENSION IF NOT EXISTS vector;

-- Contracts storage
CREATE TABLE IF NOT EXISTS contracts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  filename VARCHAR(500) NOT NULL,
  content_type VARCHAR(100) NOT NULL,
  full_text TEXT NOT NULL,
  page_count INTEGER NOT NULL,
  total_characters INTEGER NOT NULL,
  contract_type VARCHAR(100),
  status VARCHAR(20) NOT NULL DEFAULT 'pending',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_contracts_status ON contracts(status);
CREATE INDEX IF NOT EXISTS idx_contracts_type ON contracts(contract_type);

-- Document chunks with embeddings for semantic search
CREATE TABLE IF NOT EXISTS chunks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  contract_id UUID NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
  chunk_index INTEGER NOT NULL,
  text TEXT NOT NULL,
  page_start INTEGER NOT NULL,
  page_end INTEGER NOT NULL,
  character_count INTEGER NOT NULL,
  embedding VECTOR(768),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chunks_contract ON chunks(contract_id);
CREATE INDEX IF NOT EXISTS idx_chunks_embedding
  ON chunks USING hnsw (embedding vector_cosine_ops);

-- Extracted clauses
CREATE TABLE IF NOT EXISTS clauses (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  contract_id UUID NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
  clause_type VARCHAR(100) NOT NULL,
  present BOOLEAN NOT NULL,
  text_excerpt TEXT,
  page_number INTEGER,
  confidence NUMERIC(3, 2) NOT NULL,
  notes TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_clauses_contract ON clauses(contract_id);
CREATE INDEX IF NOT EXISTS idx_clauses_type ON clauses(clause_type);
CREATE INDEX IF NOT EXISTS idx_clauses_present ON clauses(contract_id, present);

-- Risk assessments
CREATE TABLE IF NOT EXISTS risks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  contract_id UUID NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
  clause_type VARCHAR(100) NOT NULL,
  risk_level VARCHAR(20) NOT NULL,
  risk_factors TEXT[] NOT NULL,
  recommendation TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_risks_contract ON risks(contract_id);
CREATE INDEX IF NOT EXISTS idx_risks_level ON risks(risk_level);

-- Analysis results
CREATE TABLE IF NOT EXISTS analyses (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  contract_id UUID NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
  overall_risk VARCHAR(20) NOT NULL,
  executive_summary TEXT NOT NULL,
  key_terms JSONB NOT NULL DEFAULT '[]',
  key_risks JSONB NOT NULL DEFAULT '[]',
  negotiation_points TEXT[],
  missing_clauses JSONB,
  parties JSONB,
  effective_date VARCHAR(50),
  expiration_date VARCHAR(50),
  governing_law VARCHAR(200),
  total_duration_ms INTEGER,
  total_tokens INTEGER,
  total_cost_usd NUMERIC(10, 6),
  trace_id VARCHAR(32),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_analyses_contract ON analyses(contract_id);
CREATE INDEX IF NOT EXISTS idx_analyses_risk ON analyses(overall_risk);

-- Auto-update updated_at on contracts
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER contracts_updated_at
  BEFORE UPDATE ON contracts
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
