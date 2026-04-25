package service

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"

	"stdlib-articles/model"

	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
)

type Notifier struct {
	url    string
	client *http.Client
}

func NewNotifier(url string) *Notifier {
	return &Notifier{
		url: url,
		client: &http.Client{
			Transport: otelhttp.NewTransport(http.DefaultTransport),
			Timeout:   5 * time.Second,
		},
	}
}

func (n *Notifier) NotifyArticleCreated(ctx context.Context, article *model.Article) error {
	if n.url == "" {
		return nil
	}

	payload := map[string]any{
		"event":      "article.created",
		"article_id": article.ID,
		"title":      article.Title,
	}
	body, err := json.Marshal(payload)
	if err != nil {
		return err
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, n.url, bytes.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := n.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	_, _ = io.Copy(io.Discard, resp.Body)

	if resp.StatusCode >= 400 {
		return fmt.Errorf("notify returned status %d", resp.StatusCode)
	}
	return nil
}
