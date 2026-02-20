import { z } from "zod";

export const CUAD_CLAUSE_TYPES = [
  "competitive_restriction",
  "exclusivity",
  "non_compete",
  "non_solicitation",
  "termination_for_convenience",
  "termination_for_cause",
  "liability_cap",
  "indemnification",
  "ip_ownership",
  "ip_license",
  "non_disclosure",
  "non_disparagement",
  "insurance",
  "audit_rights",
  "change_of_control",
  "anti_assignment",
  "warranty",
  "covenant_not_to_sue",
  "most_favored_nation",
  "price_restriction",
  "minimum_commitment",
  "volume_restriction",
  "revenue_sharing",
  "post_termination_services",
  "renewal_term",
  "unlimited_liability",
  "uncapped_liability",
  "cap_on_liability",
  "liquidated_damages",
  "rofr",
  "rofo",
  "no_solicitation_of_customers",
  "no_solicitation_of_employees",
  "force_majeure",
  "governing_law",
  "dispute_resolution",
  "arbitration",
  "notice_period",
  "consent_to_assignment",
  "data_protection",
  "survival",
] as const;

export type CUADClauseType = (typeof CUAD_CLAUSE_TYPES)[number];

export const ClauseSchema = z.object({
  clause_type: z.enum(CUAD_CLAUSE_TYPES),
  present: z.boolean(),
  text_excerpt: z.string().describe("Exact quote from the contract, empty string if not present"),
  page_number: z.number().int().min(0),
  confidence: z.number().min(0).max(1),
  notes: z.string().describe("Any qualifications, ambiguity, or context about this clause"),
});

export type Clause = z.infer<typeof ClauseSchema>;

export type RiskLevel = "critical" | "high" | "medium" | "low" | "none";
