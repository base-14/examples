package handlers

import (
	"errors"
	"strconv"

	"github.com/gofiber/fiber/v2"

	"go-fiber-postgres/internal/jobs"
	"go-fiber-postgres/internal/logging"
	"go-fiber-postgres/internal/middleware"
	"go-fiber-postgres/internal/services"
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

func (h *ArticleHandler) List(c *fiber.Ctx) error {
	limit, _ := strconv.Atoi(c.Query("limit", "20"))
	offset, _ := strconv.Atoi(c.Query("offset", "0"))

	if limit > 100 {
		limit = 100
	}

	ctx := c.UserContext()
	userID := middleware.GetUserIDPtr(c)

	result, err := h.articleService.List(ctx, limit, offset, userID)
	if err != nil {
		return middleware.ErrorResponse(c, fiber.StatusInternalServerError, "failed to list articles")
	}

	return c.JSON(result)
}

func (h *ArticleHandler) Get(c *fiber.Ctx) error {
	slug := c.Params("slug")
	ctx := c.UserContext()
	userID := middleware.GetUserIDPtr(c)

	article, err := h.articleService.GetBySlug(ctx, slug, userID)
	if err != nil {
		if errors.Is(err, services.ErrArticleNotFound) {
			return middleware.ErrorResponse(c, fiber.StatusNotFound, "article not found")
		}
		return middleware.ErrorResponse(c, fiber.StatusInternalServerError, "failed to get article")
	}

	return c.JSON(fiber.Map{
		"article": article,
	})
}

func (h *ArticleHandler) Create(c *fiber.Ctx) error {
	var input services.CreateArticleInput
	if err := c.BodyParser(&input); err != nil {
		return middleware.ErrorResponse(c, fiber.StatusBadRequest, "invalid request body")
	}

	if input.Title == "" || input.Body == "" {
		return middleware.ErrorResponse(c, fiber.StatusBadRequest, "title and body are required")
	}

	ctx := c.UserContext()
	userID := middleware.GetUserID(c)

	article, err := h.articleService.Create(ctx, userID, input)
	if err != nil {
		return middleware.ErrorResponse(c, fiber.StatusInternalServerError, "failed to create article")
	}

	if h.jobClient != nil {
		if err := h.jobClient.EnqueueNotification(ctx, article.ID, article.Title); err != nil {
			logging.Warn(ctx, "failed to enqueue notification job",
				"articleId", article.ID,
				"error", err,
			)
		}
	}

	return c.Status(fiber.StatusCreated).JSON(fiber.Map{
		"article": article,
	})
}

func (h *ArticleHandler) Update(c *fiber.Ctx) error {
	slug := c.Params("slug")
	var input services.UpdateArticleInput
	if err := c.BodyParser(&input); err != nil {
		return middleware.ErrorResponse(c, fiber.StatusBadRequest, "invalid request body")
	}

	ctx := c.UserContext()
	userID := middleware.GetUserID(c)

	article, err := h.articleService.Update(ctx, slug, userID, input)
	if err != nil {
		if errors.Is(err, services.ErrArticleNotFound) {
			return middleware.ErrorResponse(c, fiber.StatusNotFound, "article not found")
		}
		if errors.Is(err, services.ErrNotAuthor) {
			return middleware.ErrorResponse(c, fiber.StatusForbidden, "not authorized to update this article")
		}
		return middleware.ErrorResponse(c, fiber.StatusInternalServerError, "failed to update article")
	}

	return c.JSON(fiber.Map{
		"article": article,
	})
}

func (h *ArticleHandler) Delete(c *fiber.Ctx) error {
	slug := c.Params("slug")
	ctx := c.UserContext()
	userID := middleware.GetUserID(c)

	err := h.articleService.Delete(ctx, slug, userID)
	if err != nil {
		if errors.Is(err, services.ErrArticleNotFound) {
			return middleware.ErrorResponse(c, fiber.StatusNotFound, "article not found")
		}
		if errors.Is(err, services.ErrNotAuthor) {
			return middleware.ErrorResponse(c, fiber.StatusForbidden, "not authorized to delete this article")
		}
		return middleware.ErrorResponse(c, fiber.StatusInternalServerError, "failed to delete article")
	}

	return c.SendStatus(fiber.StatusNoContent)
}

func (h *ArticleHandler) Favorite(c *fiber.Ctx) error {
	slug := c.Params("slug")
	ctx := c.UserContext()
	userID := middleware.GetUserID(c)

	article, err := h.articleService.Favorite(ctx, slug, userID)
	if err != nil {
		if errors.Is(err, services.ErrArticleNotFound) {
			return middleware.ErrorResponse(c, fiber.StatusNotFound, "article not found")
		}
		if errors.Is(err, services.ErrAlreadyFavorited) {
			return middleware.ErrorResponse(c, fiber.StatusConflict, "article already favorited")
		}
		return middleware.ErrorResponse(c, fiber.StatusInternalServerError, "failed to favorite article")
	}

	return c.JSON(fiber.Map{
		"article": article,
	})
}

func (h *ArticleHandler) Unfavorite(c *fiber.Ctx) error {
	slug := c.Params("slug")
	ctx := c.UserContext()
	userID := middleware.GetUserID(c)

	article, err := h.articleService.Unfavorite(ctx, slug, userID)
	if err != nil {
		if errors.Is(err, services.ErrArticleNotFound) {
			return middleware.ErrorResponse(c, fiber.StatusNotFound, "article not found")
		}
		if errors.Is(err, services.ErrNotFavorited) {
			return middleware.ErrorResponse(c, fiber.StatusConflict, "article not favorited")
		}
		return middleware.ErrorResponse(c, fiber.StatusInternalServerError, "failed to unfavorite article")
	}

	return c.JSON(fiber.Map{
		"article": article,
	})
}
