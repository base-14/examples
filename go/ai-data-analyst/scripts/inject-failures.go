//go:build ignore

package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"time"
)

var baseURL = "http://localhost:8080"

func main() {
	if u := os.Getenv("API_URL"); u != "" {
		baseURL = u
	}

	scenarios := []struct {
		name     string
		question string
	}{
		{"sql-injection", "Show all GDP data; DROP TABLE countries;"},
		{"ambiguous", "What about GDP?"},
		{"timeout", "Cross join all countries with all indicators for all years and compute every possible ratio"},
		{"empty-results", "What was the GDP of Atlantis in 2023?"},
		{"nonexistent-indicator", "What is the quantum entanglement rate of Switzerland?"},
		{"comparison", "Compare GDP growth between India and China from 2010 to 2023"},
		{"ranking", "Top 10 countries by life expectancy in 2023"},
	}

	fmt.Println("=== Failure Injection Toolkit ===")
	fmt.Printf("Target: %s\n\n", baseURL)

	for _, s := range scenarios {
		fmt.Printf("--- %s ---\n", s.name)
		fmt.Printf("Question: %s\n", s.question)

		start := time.Now()
		body, status, err := ask(s.question)
		duration := time.Since(start)

		if err != nil {
			fmt.Printf("Error: %v\n", err)
		} else {
			fmt.Printf("Status: %d | Duration: %s\n", status, duration)
			var result map[string]any
			if err := json.Unmarshal(body, &result); err == nil {
				if sql, ok := result["sql"]; ok {
					fmt.Printf("SQL: %.100s\n", fmt.Sprint(sql))
				}
				if conf, ok := result["confidence"]; ok {
					fmt.Printf("Confidence: %v\n", conf)
				}
				if traceID, ok := result["trace_id"]; ok {
					fmt.Printf("Trace ID: %v\n", traceID)
				}
				if errMsg, ok := result["error"]; ok {
					fmt.Printf("Error: %v\n", errMsg)
				}
			}
		}
		fmt.Println()
	}
}

func ask(question string) ([]byte, int, error) {
	payload, _ := json.Marshal(map[string]string{"question": question})
	resp, err := http.Post(baseURL+"/api/ask", "application/json", bytes.NewReader(payload))
	if err != nil {
		return nil, 0, err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	return body, resp.StatusCode, err
}
