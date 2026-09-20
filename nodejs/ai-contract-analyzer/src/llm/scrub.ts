/**
 * PII scrubbing for prompt and completion text before it reaches telemetry.
 *
 * Contracts carry signatory emails, phone numbers and account identifiers.
 * Every string that goes onto a span event passes through here first.
 */

const PATTERNS: Array<{ pattern: RegExp; replacement: string }> = [
  { pattern: /\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b/g, replacement: "[EMAIL]" },
  { pattern: /\b(?:\d{4}[-\s]?){3}\d{4}\b/g, replacement: "[CREDIT_CARD]" },
  { pattern: /\b\d{3}-\d{2}-\d{4}\b/g, replacement: "[SSN]" },
  {
    pattern: /(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b/g,
    replacement: "[PHONE]",
  },
  {
    pattern: /https?:\/\/(?:www\.)?linkedin\.com\/in\/[A-Za-z0-9_-]+\/?/g,
    replacement: "[LINKEDIN_URL]",
  },
];

export function scrubPii(text: string): string {
  if (!text) return text;
  let result = text;
  for (const { pattern, replacement } of PATTERNS) {
    result = result.replace(pattern, replacement);
  }
  return result;
}
