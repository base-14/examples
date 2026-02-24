package pipeline

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestParseGenerateResponseJSON(t *testing.T) {
	content := `{"sql": "SELECT name FROM countries LIMIT 10", "explanation": "Gets country names", "tables_used": ["countries"], "confidence": 0.92}`
	r := parseGenerateResponse(content)
	assert.Equal(t, "SELECT name FROM countries LIMIT 10", r.SQL)
	assert.Equal(t, 0.92, r.Confidence)
	assert.Equal(t, []string{"countries"}, r.TablesUsed)
}

func TestParseGenerateResponseJSONBlock(t *testing.T) {
	content := "Here's the query:\n```json\n{\"sql\": \"SELECT * FROM countries\", \"explanation\": \"test\", \"tables_used\": [\"countries\"], \"confidence\": 0.85}\n```"
	r := parseGenerateResponse(content)
	assert.Equal(t, "SELECT * FROM countries", r.SQL)
	assert.Equal(t, 0.85, r.Confidence)
}

func TestParseGenerateResponseSQLBlock(t *testing.T) {
	content := "Here's the query:\n```sql\nSELECT name FROM countries\n```"
	r := parseGenerateResponse(content)
	assert.Equal(t, "SELECT name FROM countries", r.SQL)
	assert.Equal(t, 0.4, r.Confidence)
}

func TestParseGenerateResponsePlainSQL(t *testing.T) {
	content := "SELECT name FROM countries WHERE region = 'North America'"
	r := parseGenerateResponse(content)
	assert.Contains(t, r.SQL, "SELECT")
	assert.Equal(t, 0.3, r.Confidence)
}

func TestParseGenerateResponseNoSQL(t *testing.T) {
	content := "I cannot generate a query for this question."
	r := parseGenerateResponse(content)
	assert.Empty(t, r.SQL)
}

func TestBuildGeneratePrompt(t *testing.T) {
	parsed := &ParseResult{
		QuestionType: "ranking",
		Indicators:   []string{"NY.GDP.MKTP.KD.ZG"},
		Countries:    []string{"USA", "CHN"},
		TimeRange:    &TimeRange{StartYear: 2020, EndYear: 2023},
	}
	prompt := buildGeneratePrompt("Top countries by GDP growth", parsed)
	assert.Contains(t, prompt, "Top countries by GDP growth")
	assert.Contains(t, prompt, "NY.GDP.MKTP.KD.ZG")
	assert.Contains(t, prompt, "USA")
	assert.Contains(t, prompt, "2020-2023")
	assert.Contains(t, prompt, "ranking")
}
