package routes

import (
	"encoding/json"
	"net/http"

	"ai-data-analyst/internal/pipeline"
)

type AskRequest struct {
	Question string `json:"question"`
}

func AskHandler(p *pipeline.Pipeline) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		var req AskRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			writeError(w, http.StatusBadRequest, "invalid request body")
			return
		}

		if req.Question == "" {
			writeError(w, http.StatusBadRequest, "question is required")
			return
		}

		result, err := p.Ask(r.Context(), req.Question)
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}

		// If validation failed
		if result.Explanation != nil && result.SQL != "" && result.RowCount == 0 && result.Confidence < 0.3 {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusUnprocessableEntity)
			json.NewEncoder(w).Encode(result)
			return
		}

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(result)
	}
}

func writeError(w http.ResponseWriter, code int, message string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	json.NewEncoder(w).Encode(map[string]string{"error": message})
}
