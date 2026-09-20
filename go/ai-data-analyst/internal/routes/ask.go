package routes

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"strconv"

	"ai-data-analyst/internal/pipeline"
	"ai-data-analyst/internal/telemetry"
)

type AskRequest struct {
	Question string `json:"question"`
}

func AskHandler(p *pipeline.Pipeline) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		var req AskRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			writeError(r.Context(), w, http.StatusBadRequest, "invalid request body")
			return
		}

		if req.Question == "" {
			writeError(r.Context(), w, http.StatusBadRequest, "question is required")
			return
		}

		result, err := p.Ask(r.Context(), req.Question)
		if err != nil {
			writeError(r.Context(), w, http.StatusInternalServerError, err.Error())
			return
		}

		if result.Explanation != nil && result.SQL != "" && result.RowCount == 0 && result.Confidence < 0.3 {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusUnprocessableEntity)
			_ = json.NewEncoder(w).Encode(result)
			return
		}

		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(result)
	}
}

// writeError returns the error response and records it on the active span, so
// a failure handled inside a route is still visible on the trace.
func writeError(ctx context.Context, w http.ResponseWriter, code int, message string) {
	telemetry.RecordErrorOnActiveSpan(ctx, errors.New(message), strconv.Itoa(code))

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(map[string]string{"error": message})
}
