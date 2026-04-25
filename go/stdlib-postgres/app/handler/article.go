package handler

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"strconv"
	"strings"

	"stdlib-articles/model"
	"stdlib-articles/repository"

	"go.opentelemetry.io/otel/metric"
	"go.opentelemetry.io/otel/trace"
)

type ArticleHandler struct {
	repo    *repository.ArticleRepository
	notify  NotifyFunc
	logger  *slog.Logger
	created metric.Int64Counter
}

type NotifyFunc func(ctx context.Context, article *model.Article) error

func NewArticleHandler(repo *repository.ArticleRepository, notify NotifyFunc, logger *slog.Logger, created metric.Int64Counter) *ArticleHandler {
	return &ArticleHandler{repo: repo, notify: notify, logger: logger, created: created}
}

func (h *ArticleHandler) Register(mux *http.ServeMux) {
	mux.HandleFunc("GET /api/articles", h.list)
	mux.HandleFunc("GET /api/articles/{id}", h.get)
	mux.HandleFunc("POST /api/articles", h.create)
	mux.HandleFunc("PUT /api/articles/{id}", h.update)
	mux.HandleFunc("DELETE /api/articles/{id}", h.delete)
}

func (h *ArticleHandler) list(w http.ResponseWriter, r *http.Request) {
	page := parsePositiveInt(r.URL.Query().Get("page"), 1)
	perPage := parsePositiveInt(r.URL.Query().Get("per_page"), 20)
	if perPage > 100 {
		perPage = 100
	}

	articles, total, err := h.repo.List(r.Context(), page, perPage)
	if err != nil {
		h.logger.ErrorContext(r.Context(), "Failed to list articles", "error", err)
		writeError(r.Context(), w, http.StatusInternalServerError, "INTERNAL_ERROR", "Failed to list articles")
		return
	}

	h.logger.InfoContext(r.Context(), "Articles listed", "page", page, "per_page", perPage, "total", total)
	writeJSON(w, http.StatusOK, map[string]any{
		"data": articles,
		"meta": map[string]any{
			"trace_id": traceID(r.Context()),
			"page":     page,
			"per_page": perPage,
			"total":    total,
		},
	})
}

func (h *ArticleHandler) get(w http.ResponseWriter, r *http.Request) {
	id, ok := h.parseID(w, r)
	if !ok {
		return
	}

	article, err := h.repo.GetByID(r.Context(), id)
	if errors.Is(err, repository.ErrNotFound) {
		h.logger.WarnContext(r.Context(), "Article not found", "article_id", id)
		writeError(r.Context(), w, http.StatusNotFound, "NOT_FOUND", "Article not found")
		return
	}
	if err != nil {
		h.logger.ErrorContext(r.Context(), "Failed to fetch article", "error", err, "article_id", id)
		writeError(r.Context(), w, http.StatusInternalServerError, "INTERNAL_ERROR", "Failed to fetch article")
		return
	}

	h.logger.InfoContext(r.Context(), "Article fetched", "article_id", id)
	writeJSON(w, http.StatusOK, envelope(r.Context(), article))
}

func (h *ArticleHandler) create(w http.ResponseWriter, r *http.Request) {
	var req model.CreateArticleRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		h.logger.WarnContext(r.Context(), "Validation failed: invalid JSON", "error", err)
		writeError(r.Context(), w, http.StatusUnprocessableEntity, "VALIDATION_FAILED", "Invalid JSON body")
		return
	}
	req.Title = strings.TrimSpace(req.Title)
	req.Body = strings.TrimSpace(req.Body)
	if req.Title == "" || req.Body == "" {
		h.logger.WarnContext(r.Context(), "Validation failed: title and body required")
		writeError(r.Context(), w, http.StatusUnprocessableEntity, "VALIDATION_FAILED", "title and body are required")
		return
	}
	if len(req.Title) > 255 {
		h.logger.WarnContext(r.Context(), "Validation failed: title too long")
		writeError(r.Context(), w, http.StatusUnprocessableEntity, "VALIDATION_FAILED", "title must be <= 255 chars")
		return
	}

	article, err := h.repo.Create(r.Context(), req.Title, req.Body)
	if err != nil {
		h.logger.ErrorContext(r.Context(), "Failed to create article", "error", err)
		writeError(r.Context(), w, http.StatusInternalServerError, "INTERNAL_ERROR", "Failed to create article")
		return
	}

	h.created.Add(r.Context(), 1)
	h.logger.InfoContext(r.Context(), "Article created", "article_id", article.ID)

	if h.notify != nil {
		if err := h.notify(r.Context(), article); err != nil {
			h.logger.ErrorContext(r.Context(), "Notification failed", "error", err, "article_id", article.ID)
		} else {
			h.logger.InfoContext(r.Context(), "Notification sent", "article_id", article.ID)
		}
	}

	writeJSON(w, http.StatusCreated, envelope(r.Context(), article))
}

func (h *ArticleHandler) update(w http.ResponseWriter, r *http.Request) {
	id, ok := h.parseID(w, r)
	if !ok {
		return
	}

	var req model.UpdateArticleRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		h.logger.WarnContext(r.Context(), "Validation failed: invalid JSON", "error", err)
		writeError(r.Context(), w, http.StatusUnprocessableEntity, "VALIDATION_FAILED", "Invalid JSON body")
		return
	}
	if req.Title == nil && req.Body == nil {
		h.logger.WarnContext(r.Context(), "Validation failed: title or body required")
		writeError(r.Context(), w, http.StatusUnprocessableEntity, "VALIDATION_FAILED", "title or body is required")
		return
	}
	if req.Title != nil {
		trimmed := strings.TrimSpace(*req.Title)
		if trimmed == "" {
			h.logger.WarnContext(r.Context(), "Validation failed: title must not be empty")
			writeError(r.Context(), w, http.StatusUnprocessableEntity, "VALIDATION_FAILED", "title must not be empty")
			return
		}
		if len(trimmed) > 255 {
			h.logger.WarnContext(r.Context(), "Validation failed: title too long")
			writeError(r.Context(), w, http.StatusUnprocessableEntity, "VALIDATION_FAILED", "title must be <= 255 chars")
			return
		}
		req.Title = &trimmed
	}
	if req.Body != nil {
		trimmed := strings.TrimSpace(*req.Body)
		if trimmed == "" {
			h.logger.WarnContext(r.Context(), "Validation failed: body must not be empty")
			writeError(r.Context(), w, http.StatusUnprocessableEntity, "VALIDATION_FAILED", "body must not be empty")
			return
		}
		req.Body = &trimmed
	}

	article, err := h.repo.Update(r.Context(), id, req.Title, req.Body)
	if errors.Is(err, repository.ErrNotFound) {
		h.logger.WarnContext(r.Context(), "Article not found", "article_id", id)
		writeError(r.Context(), w, http.StatusNotFound, "NOT_FOUND", "Article not found")
		return
	}
	if err != nil {
		h.logger.ErrorContext(r.Context(), "Failed to update article", "error", err, "article_id", id)
		writeError(r.Context(), w, http.StatusInternalServerError, "INTERNAL_ERROR", "Failed to update article")
		return
	}

	h.logger.InfoContext(r.Context(), "Article updated", "article_id", id)
	writeJSON(w, http.StatusOK, envelope(r.Context(), article))
}

func (h *ArticleHandler) delete(w http.ResponseWriter, r *http.Request) {
	id, ok := h.parseID(w, r)
	if !ok {
		return
	}

	err := h.repo.Delete(r.Context(), id)
	if errors.Is(err, repository.ErrNotFound) {
		h.logger.WarnContext(r.Context(), "Article not found", "article_id", id)
		writeError(r.Context(), w, http.StatusNotFound, "NOT_FOUND", "Article not found")
		return
	}
	if err != nil {
		h.logger.ErrorContext(r.Context(), "Failed to delete article", "error", err, "article_id", id)
		writeError(r.Context(), w, http.StatusInternalServerError, "INTERNAL_ERROR", "Failed to delete article")
		return
	}

	h.logger.InfoContext(r.Context(), "Article deleted", "article_id", id)
	w.WriteHeader(http.StatusNoContent)
}

func (h *ArticleHandler) parseID(w http.ResponseWriter, r *http.Request) (int64, bool) {
	raw := r.PathValue("id")
	id, err := strconv.ParseInt(raw, 10, 64)
	if err != nil || id <= 0 {
		h.logger.WarnContext(r.Context(), "Invalid article ID", "raw", raw)
		writeError(r.Context(), w, http.StatusBadRequest, "INVALID_ID", "Invalid article ID")
		return 0, false
	}
	return id, true
}

func parsePositiveInt(s string, def int) int {
	if s == "" {
		return def
	}
	n, err := strconv.Atoi(s)
	if err != nil || n < 1 {
		return def
	}
	return n
}

func envelope(ctx context.Context, data any) map[string]any {
	return map[string]any{
		"data": data,
		"meta": map[string]any{"trace_id": traceID(ctx)},
	}
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func writeError(ctx context.Context, w http.ResponseWriter, status int, code, message string) {
	writeJSON(w, status, map[string]any{
		"error": map[string]string{"code": code, "message": message},
		"meta":  map[string]any{"trace_id": traceID(ctx)},
	})
}

func traceID(ctx context.Context) string {
	sc := trace.SpanFromContext(ctx).SpanContext()
	if !sc.IsValid() {
		return ""
	}
	return sc.TraceID().String()
}
