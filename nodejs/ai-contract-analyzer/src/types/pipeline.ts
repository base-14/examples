import type { Clause, CUADClauseType, RiskLevel } from "./clauses.ts";

export interface ChunkData {
  index: number;
  text: string;
  page_start: number;
  page_end: number;
  character_count: number;
}

export interface IngestResult {
  contract_id: string;
  filename: string;
  page_count: number;
  total_characters: number;
  chunks: ChunkData[];
  full_text: string;
}

export interface Party {
  name: string;
  role: "party_a" | "party_b" | "third_party";
}

export interface ExtractionResult {
  clauses: Clause[];
  parties: Party[];
  effective_date: string | null;
  expiration_date: string | null;
  governing_law: string | null;
  contract_type: string;
}

export interface ClauseRisk {
  clause_type: CUADClauseType;
  risk_level: RiskLevel;
  risk_factors: string[];
  recommendation: string;
}

export interface MissingClause {
  clause_type: CUADClauseType;
  importance: "required" | "recommended" | "optional";
  explanation: string;
}

export interface RiskResult {
  clause_risks: ClauseRisk[];
  overall_risk: Exclude<RiskLevel, "none">;
  missing_clauses: MissingClause[];
}

export interface KeyTerm {
  term: string;
  value: string;
}

export interface KeyRisk {
  risk: string;
  severity: string;
  recommendation: string;
}

export interface SummaryResult {
  executive_summary: string;
  key_terms: KeyTerm[];
  key_risks: KeyRisk[];
  negotiation_points: string[];
}

export interface AnalysisResult {
  ingest: IngestResult;
  extraction: ExtractionResult;
  risks: RiskResult;
  summary: SummaryResult;
  total_duration_ms: number;
  total_tokens: number;
  total_cost_usd: number;
  trace_id?: string;
}
