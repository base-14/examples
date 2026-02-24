package routes

import (
	"encoding/json"
	"net/http"

	"ai-data-analyst/internal/db"
)

func IndicatorsHandler(q db.Querier) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		indicators, err := db.ListIndicators(r.Context(), q)
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(indicators)
	}
}
