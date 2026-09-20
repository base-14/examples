package llm

import (
	"regexp"
	"strings"
)

type piiPattern struct {
	pattern     *regexp.Regexp
	replacement string
}

var piiPatterns = []piiPattern{
	{regexp.MustCompile(`\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b`), "[EMAIL]"},
	{regexp.MustCompile(`\b\d(?:[ -]?\d){12,15}\b`), "[CARD]"},
	{regexp.MustCompile(`(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b`), "[PHONE]"},
}

// scrubPII replaces email addresses, card-like digit runs and phone numbers
// with placeholders. Questions and SQL reach telemetry as free text, so they
// are scrubbed before any content is recorded on a span.
func scrubPII(text string) string {
	for _, p := range piiPatterns {
		text = p.pattern.ReplaceAllString(text, p.replacement)
	}
	return text
}

// truncateRunes cuts text to at most max runes, so a multi-byte character is
// never split in half.
func truncateRunes(text string, max int) string {
	if len(text) <= max {
		return text
	}
	runes := []rune(text)
	if len(runes) <= max {
		return text
	}
	return string(runes[:max])
}

func scrubAndTruncate(text string, max int) string {
	return truncateRunes(strings.TrimSpace(scrubPII(text)), max)
}
