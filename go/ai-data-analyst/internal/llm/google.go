package llm

import (
	openai "github.com/sashabaranov/go-openai"
)

const googleBaseURL = "https://generativelanguage.googleapis.com/v1beta/openai"

func NewGoogleProvider(apiKey string) *OpenAIProvider {
	cfg := openai.DefaultConfig(apiKey)
	cfg.BaseURL = googleBaseURL
	return &OpenAIProvider{client: openai.NewClientWithConfig(cfg)}
}
