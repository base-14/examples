export type ContractStatus = "pending" | "processing" | "complete" | "error";

export interface ContractRow {
  id: string;
  filename: string;
  content_type: string;
  full_text: string;
  page_count: number;
  total_characters: number;
  contract_type: string | null;
  status: ContractStatus;
  created_at: Date;
  updated_at: Date;
}

export interface ContractSummary {
  id: string;
  filename: string;
  contract_type: string | null;
  status: ContractStatus;
  created_at: Date;
}

export interface AnalysisRow {
  id: string;
  contract_id: string;
  overall_risk: string;
  executive_summary: string;
  key_terms: Array<{ term: string; value: string }>;
  key_risks: Array<{ risk: string; severity: string; recommendation: string }>;
  negotiation_points: string[] | null;
  missing_clauses: unknown;
  parties: unknown;
  effective_date: string | null;
  expiration_date: string | null;
  governing_law: string | null;
  total_duration_ms: number | null;
  total_tokens: number | null;
  total_cost_usd: string | null;
  trace_id: string | null;
  created_at: Date;
}
