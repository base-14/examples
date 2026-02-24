package db

import (
	"context"
	"time"
)

type QueryHistory struct {
	ID           string    `json:"id"`
	Question     string    `json:"question"`
	QuestionType string    `json:"question_type"`
	GeneratedSQL string    `json:"generated_sql"`
	Confidence   float64   `json:"confidence"`
	RowCount     int       `json:"row_count"`
	ExecutionMS  int       `json:"execution_ms"`
	TotalTokens  int       `json:"total_tokens"`
	TotalCostUSD float64   `json:"total_cost_usd"`
	Explanation  string    `json:"explanation"`
	TraceID      string    `json:"trace_id"`
	CreatedAt    time.Time `json:"created_at"`
}

type InsertHistoryParams struct {
	Question     string
	QuestionType string
	GeneratedSQL string
	Confidence   float64
	RowCount     int
	ExecutionMS  int
	TotalTokens  int
	TotalCostUSD float64
	Explanation  string
	TraceID      string
}

func InsertQueryHistory(ctx context.Context, q Querier, p InsertHistoryParams) (string, error) {
	var id string
	err := q.QueryRow(ctx, `
		INSERT INTO query_history (question, question_type, generated_sql, confidence, row_count,
			execution_ms, total_tokens, total_cost_usd, explanation, trace_id)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
		RETURNING id`,
		p.Question, p.QuestionType, p.GeneratedSQL, p.Confidence, p.RowCount,
		p.ExecutionMS, p.TotalTokens, p.TotalCostUSD, p.Explanation, p.TraceID,
	).Scan(&id)
	return id, err
}

func ListHistory(ctx context.Context, q Querier, limit, offset int) ([]QueryHistory, error) {
	if limit <= 0 {
		limit = 20
	}
	rows, err := q.Query(ctx, `
		SELECT id, question, COALESCE(question_type, ''), generated_sql,
			COALESCE(confidence, 0), COALESCE(row_count, 0), COALESCE(execution_ms, 0),
			COALESCE(total_tokens, 0), COALESCE(total_cost_usd, 0),
			COALESCE(explanation, ''), COALESCE(trace_id, ''), created_at
		FROM query_history
		ORDER BY created_at DESC
		LIMIT $1 OFFSET $2`, limit, offset)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var history []QueryHistory
	for rows.Next() {
		var h QueryHistory
		if err := rows.Scan(&h.ID, &h.Question, &h.QuestionType, &h.GeneratedSQL,
			&h.Confidence, &h.RowCount, &h.ExecutionMS, &h.TotalTokens,
			&h.TotalCostUSD, &h.Explanation, &h.TraceID, &h.CreatedAt); err != nil {
			return nil, err
		}
		history = append(history, h)
	}
	return history, rows.Err()
}
