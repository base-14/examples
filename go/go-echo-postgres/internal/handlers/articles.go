package handlers

import (
	"errors"
	"net/http"
	"strconv"

	"go-echo-postgres/internal/jobs"
	"go-echo-postgres/internal/middleware"
	"go-echo-postgres/internal/services"

	"github.com/labstack/echo/v4"
)

type ArticleHandler struct {
	articleService *services.ArticleService
	jobClient      *jobs.Client
}

func NewArticleHandler(articleService *services.ArticleService, jobClient *jobs.Client) *ArticleHandler {
	return &ArticleHandler{
		articleService: articleService,
		jobClient:      jobClient,
	}
}

func (h *ArticleHandler) List(c echo.Context) error {
	ctx := c.Request().Context()

	page, _ := strconv.Atoi(c.QueryParam("page"))
	perPage, _ := strconv.Atoi(c.QueryParam("per_page"))
	search := c.QueryParam("search")
	author := c.QueryParam("author")

	if page < 1 {
		page = 1
	}
	if perPage < 1 || perPage > 100 {
		perPage = 20
	}

	input := services.ListArticlesInput{
		Page:    page,
		PerPage: perPage,
		Search:  search,
		Author:  author,
	}

	var userID *uint
	if id, ok := middleware.GetUserID(c); ok {
		userID = &id
	}

	result, err := h.articleService.ListWithFavorites(ctx, userID, input)
	if err != nil {
		return echo.NewHTTPError(http.StatusInternalServerError, "failed to list articles")
	}

	return c.JSON(http.StatusOK, result)
}

func (h *ArticleHandler) Create(c echo.Context) error {
	ctx := c.Request().Context()

	userID, ok := middleware.GetUserID(c)
	if !ok {
		return echo.NewHTTPError(http.StatusUnauthorized, "unauthorized")
	}

	var input services.CreateArticleInput
	if err := c.Bind(&input); err != nil {
		return echo.NewHTTPError(http.StatusBadRequest, "invalid request body")
	}

	if input.Title == "" || input.Body == "" {
		return echo.NewHTTPError(http.StatusBadRequest, "title and body are required")
	}

	article, err := h.articleService.Create(ctx, userID, input)
	if err != nil {
		return echo.NewHTTPError(http.StatusInternalServerError, "failed to create article")
	}

	if h.jobClient != nil {
		h.jobClient.EnqueueNotification(ctx, article.ID, article.Title)
	}

	favorited := false
	return c.JSON(http.StatusCreated, map[string]interface{}{
		"article": article.ToResponse(favorited),
	})
}

func (h *ArticleHandler) Get(c echo.Context) error {
	ctx := c.Request().Context()
	slug := c.Param("slug")

	article, err := h.articleService.GetBySlug(ctx, slug)
	if err != nil {
		if errors.Is(err, services.ErrArticleNotFound) {
			return echo.NewHTTPError(http.StatusNotFound, "article not found")
		}
		return echo.NewHTTPError(http.StatusInternalServerError, "failed to get article")
	}

	favorited := false
	if userID, ok := middleware.GetUserID(c); ok {
		favorited = h.articleService.IsFavorited(ctx, article.ID, userID)
	}

	return c.JSON(http.StatusOK, map[string]interface{}{
		"article": article.ToResponse(favorited),
	})
}

func (h *ArticleHandler) Update(c echo.Context) error {
	ctx := c.Request().Context()
	slug := c.Param("slug")

	userID, ok := middleware.GetUserID(c)
	if !ok {
		return echo.NewHTTPError(http.StatusUnauthorized, "unauthorized")
	}

	var input services.UpdateArticleInput
	if err := c.Bind(&input); err != nil {
		return echo.NewHTTPError(http.StatusBadRequest, "invalid request body")
	}

	article, err := h.articleService.Update(ctx, slug, userID, input)
	if err != nil {
		if errors.Is(err, services.ErrArticleNotFound) {
			return echo.NewHTTPError(http.StatusNotFound, "article not found")
		}
		if errors.Is(err, services.ErrNotAuthor) {
			return echo.NewHTTPError(http.StatusForbidden, "you are not the author of this article")
		}
		return echo.NewHTTPError(http.StatusInternalServerError, "failed to update article")
	}

	favorited := h.articleService.IsFavorited(ctx, article.ID, userID)
	return c.JSON(http.StatusOK, map[string]interface{}{
		"article": article.ToResponse(favorited),
	})
}

func (h *ArticleHandler) Delete(c echo.Context) error {
	ctx := c.Request().Context()
	slug := c.Param("slug")

	userID, ok := middleware.GetUserID(c)
	if !ok {
		return echo.NewHTTPError(http.StatusUnauthorized, "unauthorized")
	}

	err := h.articleService.Delete(ctx, slug, userID)
	if err != nil {
		if errors.Is(err, services.ErrArticleNotFound) {
			return echo.NewHTTPError(http.StatusNotFound, "article not found")
		}
		if errors.Is(err, services.ErrNotAuthor) {
			return echo.NewHTTPError(http.StatusForbidden, "you are not the author of this article")
		}
		return echo.NewHTTPError(http.StatusInternalServerError, "failed to delete article")
	}

	return c.NoContent(http.StatusNoContent)
}

func (h *ArticleHandler) Favorite(c echo.Context) error {
	ctx := c.Request().Context()
	slug := c.Param("slug")

	userID, ok := middleware.GetUserID(c)
	if !ok {
		return echo.NewHTTPError(http.StatusUnauthorized, "unauthorized")
	}

	article, err := h.articleService.Favorite(ctx, slug, userID)
	if err != nil {
		if errors.Is(err, services.ErrArticleNotFound) {
			return echo.NewHTTPError(http.StatusNotFound, "article not found")
		}
		if errors.Is(err, services.ErrAlreadyFavorited) {
			return echo.NewHTTPError(http.StatusConflict, "article already favorited")
		}
		return echo.NewHTTPError(http.StatusInternalServerError, "failed to favorite article")
	}

	return c.JSON(http.StatusOK, map[string]interface{}{
		"article": article.ToResponse(true),
	})
}

func (h *ArticleHandler) Unfavorite(c echo.Context) error {
	ctx := c.Request().Context()
	slug := c.Param("slug")

	userID, ok := middleware.GetUserID(c)
	if !ok {
		return echo.NewHTTPError(http.StatusUnauthorized, "unauthorized")
	}

	article, err := h.articleService.Unfavorite(ctx, slug, userID)
	if err != nil {
		if errors.Is(err, services.ErrArticleNotFound) {
			return echo.NewHTTPError(http.StatusNotFound, "article not found")
		}
		if errors.Is(err, services.ErrNotFavorited) {
			return echo.NewHTTPError(http.StatusConflict, "article not favorited")
		}
		return echo.NewHTTPError(http.StatusInternalServerError, "failed to unfavorite article")
	}

	return c.JSON(http.StatusOK, map[string]interface{}{
		"article": article.ToResponse(false),
	})
}
