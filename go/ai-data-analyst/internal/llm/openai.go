package llm

import (
	"context"

	openai "github.com/sashabaranov/go-openai"
)

type OpenAIProvider struct {
	client  *openai.Client
	name    string
	address string
	port    int
}

func NewOpenAIProvider(apiKey string) *OpenAIProvider {
	return &OpenAIProvider{
		client:  openai.NewClient(apiKey),
		name:    "openai",
		address: "api.openai.com",
		port:    443,
	}
}

func NewOllamaProvider(baseURL string) *OpenAIProvider {
	cfg := openai.DefaultConfig("ollama")
	cfg.BaseURL = baseURL + "/v1"
	address, port := parseServerURL(baseURL, defaultOllamaHost, defaultOllamaPort)
	return &OpenAIProvider{
		client:  openai.NewClientWithConfig(cfg),
		name:    "ollama",
		address: address,
		port:    port,
	}
}

func (p *OpenAIProvider) Name() string { return p.name }

func (p *OpenAIProvider) ServerAddress() string { return p.address }

func (p *OpenAIProvider) ServerPort() int { return p.port }

func (p *OpenAIProvider) Generate(ctx context.Context, req GenerateRequest) (*GenerateResponse, error) {
	messages := []openai.ChatCompletionMessage{
		{Role: openai.ChatMessageRoleSystem, Content: req.System},
		{Role: openai.ChatMessageRoleUser, Content: req.Prompt},
	}

	resp, err := p.client.CreateChatCompletion(ctx, openai.ChatCompletionRequest{
		Model:       req.Model,
		Messages:    messages,
		Temperature: float32(req.Temperature),
		MaxTokens:   req.MaxTokens,
	})
	if err != nil {
		return nil, err
	}

	content := ""
	finishReason := ""
	if len(resp.Choices) > 0 {
		content = resp.Choices[0].Message.Content
		finishReason = string(resp.Choices[0].FinishReason)
	}

	return &GenerateResponse{
		Content:      content,
		Model:        resp.Model,
		ResponseID:   resp.ID,
		InputTokens:  resp.Usage.PromptTokens,
		OutputTokens: resp.Usage.CompletionTokens,
		FinishReason: finishReason,
	}, nil
}
