package llm

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestScrubPII(t *testing.T) {
	tests := []struct {
		name     string
		in       string
		expected string
	}{
		{"email", "write to ops@example.com today", "write to [EMAIL] today"},
		{"phone", "call 415-555-0100 now", "call [PHONE] now"},
		{"card", "card 4111 1111 1111 1111 expires", "card [CARD] expires"},
		{"clean text", "SELECT name FROM countries", "SELECT name FROM countries"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			assert.Equal(t, tt.expected, scrubPII(tt.in))
		})
	}
}

func TestTruncateRunesKeepsCharactersWhole(t *testing.T) {
	assert.Equal(t, "héllo", truncateRunes("héllo wörld", 5))
	assert.Equal(t, "短い", truncateRunes("短い文", 2))
	assert.Equal(t, "abc", truncateRunes("abc", 10))
}

func TestScrubAndTruncate(t *testing.T) {
	assert.Equal(t, "[EMAIL]", scrubAndTruncate("  ops@example.com  ", 100))
	assert.Equal(t, "ab", scrubAndTruncate("abcdef", 2))
}
