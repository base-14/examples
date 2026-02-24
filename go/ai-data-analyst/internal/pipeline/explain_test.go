package pipeline

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestParseExplainResponseJSON(t *testing.T) {
	content := `{"summary": "The top countries by GDP are...", "insights": ["China leads", "India growing fast"], "caveats": ["Data from 2023"], "follow_ups": ["What about 2024?"]}`
	r := parseExplainResponse(content)
	assert.Equal(t, "The top countries by GDP are...", r.Summary)
	assert.Len(t, r.Insights, 2)
	assert.Len(t, r.Caveats, 1)
	assert.Len(t, r.FollowUps, 1)
}

func TestParseExplainResponsePlainText(t *testing.T) {
	content := "The data shows that GDP growth was highest in India at 7.2%."
	r := parseExplainResponse(content)
	assert.Contains(t, r.Summary, "GDP growth")
}

func TestBuildExplainPromptWithData(t *testing.T) {
	execResult := &ExecuteResult{
		Columns:  []string{"country", "gdp_growth"},
		Rows:     [][]any{{"India", 7.2}, {"China", 5.1}},
		RowCount: 2,
	}
	prompt := buildExplainPrompt("Top countries by GDP growth", "SELECT ...", execResult)
	assert.Contains(t, prompt, "Top countries by GDP growth")
	assert.Contains(t, prompt, "2 rows")
	assert.Contains(t, prompt, "India")
}

func TestBuildExplainPromptEmptyResults(t *testing.T) {
	execResult := &ExecuteResult{
		Columns:  []string{},
		Rows:     nil,
		RowCount: 0,
	}
	prompt := buildExplainPrompt("GDP of Atlantis", "SELECT ...", execResult)
	assert.Contains(t, prompt, "No data returned")
	assert.Contains(t, prompt, "broaden")
}
