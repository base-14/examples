package services

import (
	"context"
	"errors"
	"fmt"
	"regexp"
	"strings"
	"time"

	"go-echo-postgres/internal/database"
	"go-echo-postgres/internal/logging"
	"go-echo-postgres/internal/models"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"
	"gorm.io/gorm"
)

var (
	ErrArticleNotFound = errors.New("article not found")
	ErrNotAuthor       = errors.New("not the author of this article")
	ErrAlreadyFavorited = errors.New("article already favorited")
	ErrNotFavorited    = errors.New("article not favorited")
)

var articlesCreatedCounter metric.Int64Counter

type ArticleService struct{}

func NewArticleService() *ArticleService {
	var err error
	articlesCreatedCounter, err = meter.Int64Counter(
		"articles.created",
		metric.WithDescription("Total number of articles created"),
	)
	if err != nil {
		logging.Logger().Error().Err(err).Msg("failed to create articles counter")
	}

	return &ArticleService{}
}

type CreateArticleInput struct {
	Title       string `json:"title" validate:"required"`
	Description string `json:"description"`
	Body        string `json:"body" validate:"required"`
}

type UpdateArticleInput struct {
	Title       *string `json:"title"`
	Description *string `json:"description"`
	Body        *string `json:"body"`
}

type ListArticlesInput struct {
	Page    int
	PerPage int
	Search  string
	Author  string
}

func (s *ArticleService) Create(ctx context.Context, authorID uint, input CreateArticleInput) (*models.Article, error) {
	ctx, span := tracer.Start(ctx, "article.create")
	defer span.End()

	span.SetAttributes(
		attribute.Int64("author.id", int64(authorID)),
		attribute.String("article.title", input.Title),
	)

	slug := generateSlug(input.Title)

	var existingCount int64
	database.DB.WithContext(ctx).Model(&models.Article{}).Where("slug LIKE ?", slug+"%").Count(&existingCount)
	if existingCount > 0 {
		slug = fmt.Sprintf("%s-%d", slug, time.Now().UnixNano())
	}

	article := models.Article{
		Slug:        slug,
		Title:       input.Title,
		Description: input.Description,
		Body:        input.Body,
		AuthorID:    authorID,
	}

	if err := database.DB.WithContext(ctx).Create(&article).Error; err != nil {
		return nil, err
	}

	if err := database.DB.WithContext(ctx).Preload("Author").First(&article, article.ID).Error; err != nil {
		return nil, err
	}

	if articlesCreatedCounter != nil {
		articlesCreatedCounter.Add(ctx, 1)
	}

	span.SetAttributes(
		attribute.Int64("article.id", int64(article.ID)),
		attribute.String("article.slug", article.Slug),
	)

	logging.Info(ctx).
		Uint("article_id", article.ID).
		Str("slug", article.Slug).
		Uint("author_id", authorID).
		Msg("article created")

	return &article, nil
}

func (s *ArticleService) GetBySlug(ctx context.Context, slug string) (*models.Article, error) {
	ctx, span := tracer.Start(ctx, "article.get_by_slug")
	defer span.End()

	span.SetAttributes(attribute.String("article.slug", slug))

	var article models.Article
	if err := database.DB.WithContext(ctx).Preload("Author").Where("slug = ?", slug).First(&article).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, ErrArticleNotFound
		}
		return nil, err
	}

	return &article, nil
}

func (s *ArticleService) List(ctx context.Context, input ListArticlesInput) (*models.ArticlesResponse, error) {
	ctx, span := tracer.Start(ctx, "article.list")
	defer span.End()

	if input.Page < 1 {
		input.Page = 1
	}
	if input.PerPage < 1 || input.PerPage > 100 {
		input.PerPage = 20
	}

	span.SetAttributes(
		attribute.Int("pagination.page", input.Page),
		attribute.Int("pagination.per_page", input.PerPage),
	)

	query := database.DB.WithContext(ctx).Model(&models.Article{})

	if input.Search != "" {
		searchTerm := "%" + input.Search + "%"
		query = query.Where("title ILIKE ? OR description ILIKE ?", searchTerm, searchTerm)
		span.SetAttributes(attribute.String("search.term", input.Search))
	}

	if input.Author != "" {
		query = query.Joins("JOIN users ON users.id = articles.author_id").
			Where("users.name ILIKE ?", "%"+input.Author+"%")
		span.SetAttributes(attribute.String("filter.author", input.Author))
	}

	var totalCount int64
	if err := query.Count(&totalCount).Error; err != nil {
		return nil, err
	}

	offset := (input.Page - 1) * input.PerPage
	var articles []models.Article
	if err := query.
		Preload("Author").
		Order("created_at DESC").
		Offset(offset).
		Limit(input.PerPage).
		Find(&articles).Error; err != nil {
		return nil, err
	}

	span.SetAttributes(
		attribute.Int64("result.total_count", totalCount),
		attribute.Int("result.count", len(articles)),
	)

	return &models.ArticlesResponse{
		Articles:   make([]models.ArticleResponse, 0),
		TotalCount: totalCount,
		Page:       input.Page,
		PerPage:    input.PerPage,
	}, nil
}

func (s *ArticleService) ListWithFavorites(ctx context.Context, userID *uint, input ListArticlesInput) (*models.ArticlesResponse, error) {
	ctx, span := tracer.Start(ctx, "article.list_with_favorites")
	defer span.End()

	if input.Page < 1 {
		input.Page = 1
	}
	if input.PerPage < 1 || input.PerPage > 100 {
		input.PerPage = 20
	}

	query := database.DB.WithContext(ctx).Model(&models.Article{})

	if input.Search != "" {
		searchTerm := "%" + input.Search + "%"
		query = query.Where("title ILIKE ? OR description ILIKE ?", searchTerm, searchTerm)
	}

	if input.Author != "" {
		query = query.Joins("JOIN users ON users.id = articles.author_id").
			Where("users.name ILIKE ?", "%"+input.Author+"%")
	}

	var totalCount int64
	if err := query.Count(&totalCount).Error; err != nil {
		return nil, err
	}

	offset := (input.Page - 1) * input.PerPage
	var articles []models.Article
	if err := query.
		Preload("Author").
		Order("created_at DESC").
		Offset(offset).
		Limit(input.PerPage).
		Find(&articles).Error; err != nil {
		return nil, err
	}

	var favoritedMap map[uint]bool
	if userID != nil {
		favoritedMap = make(map[uint]bool)
		articleIDs := make([]uint, len(articles))
		for i, a := range articles {
			articleIDs[i] = a.ID
		}

		var favorites []models.Favorite
		database.DB.WithContext(ctx).
			Where("user_id = ? AND article_id IN ?", *userID, articleIDs).
			Find(&favorites)

		for _, f := range favorites {
			favoritedMap[f.ArticleID] = true
		}
	}

	responses := make([]models.ArticleResponse, len(articles))
	for i, article := range articles {
		favorited := false
		if favoritedMap != nil {
			favorited = favoritedMap[article.ID]
		}
		responses[i] = article.ToResponse(favorited)
	}

	return &models.ArticlesResponse{
		Articles:   responses,
		TotalCount: totalCount,
		Page:       input.Page,
		PerPage:    input.PerPage,
	}, nil
}

func (s *ArticleService) Update(ctx context.Context, slug string, userID uint, input UpdateArticleInput) (*models.Article, error) {
	ctx, span := tracer.Start(ctx, "article.update")
	defer span.End()

	span.SetAttributes(
		attribute.String("article.slug", slug),
		attribute.Int64("user.id", int64(userID)),
	)

	article, err := s.GetBySlug(ctx, slug)
	if err != nil {
		return nil, err
	}

	if article.AuthorID != userID {
		return nil, ErrNotAuthor
	}

	updates := make(map[string]interface{})
	if input.Title != nil {
		updates["title"] = *input.Title
		updates["slug"] = generateSlug(*input.Title)
	}
	if input.Description != nil {
		updates["description"] = *input.Description
	}
	if input.Body != nil {
		updates["body"] = *input.Body
	}

	if len(updates) > 0 {
		if err := database.DB.WithContext(ctx).Model(article).Updates(updates).Error; err != nil {
			return nil, err
		}
		if err := database.DB.WithContext(ctx).Preload("Author").First(article, article.ID).Error; err != nil {
			return nil, err
		}
	}

	logging.Info(ctx).
		Uint("article_id", article.ID).
		Str("slug", article.Slug).
		Msg("article updated")

	return article, nil
}

func (s *ArticleService) Delete(ctx context.Context, slug string, userID uint) error {
	ctx, span := tracer.Start(ctx, "article.delete")
	defer span.End()

	span.SetAttributes(
		attribute.String("article.slug", slug),
		attribute.Int64("user.id", int64(userID)),
	)

	article, err := s.GetBySlug(ctx, slug)
	if err != nil {
		return err
	}

	if article.AuthorID != userID {
		return ErrNotAuthor
	}

	if err := database.DB.WithContext(ctx).Delete(article).Error; err != nil {
		return err
	}

	logging.Info(ctx).
		Uint("article_id", article.ID).
		Str("slug", slug).
		Msg("article deleted")

	return nil
}

func (s *ArticleService) Favorite(ctx context.Context, slug string, userID uint) (*models.Article, error) {
	ctx, span := tracer.Start(ctx, "article.favorite")
	defer span.End()

	span.SetAttributes(
		attribute.String("article.slug", slug),
		attribute.Int64("user.id", int64(userID)),
	)

	article, err := s.GetBySlug(ctx, slug)
	if err != nil {
		return nil, err
	}

	var existing models.Favorite
	if err := database.DB.WithContext(ctx).
		Where("user_id = ? AND article_id = ?", userID, article.ID).
		First(&existing).Error; err == nil {
		return nil, ErrAlreadyFavorited
	}

	favorite := models.Favorite{
		UserID:    userID,
		ArticleID: article.ID,
	}

	if err := database.DB.WithContext(ctx).Create(&favorite).Error; err != nil {
		return nil, err
	}

	if err := database.DB.WithContext(ctx).
		Model(article).
		Update("favorites_count", gorm.Expr("favorites_count + 1")).Error; err != nil {
		return nil, err
	}

	if err := database.DB.WithContext(ctx).Preload("Author").First(article, article.ID).Error; err != nil {
		return nil, err
	}

	logging.Info(ctx).
		Uint("article_id", article.ID).
		Uint("user_id", userID).
		Msg("article favorited")

	return article, nil
}

func (s *ArticleService) Unfavorite(ctx context.Context, slug string, userID uint) (*models.Article, error) {
	ctx, span := tracer.Start(ctx, "article.unfavorite")
	defer span.End()

	span.SetAttributes(
		attribute.String("article.slug", slug),
		attribute.Int64("user.id", int64(userID)),
	)

	article, err := s.GetBySlug(ctx, slug)
	if err != nil {
		return nil, err
	}

	result := database.DB.WithContext(ctx).
		Where("user_id = ? AND article_id = ?", userID, article.ID).
		Delete(&models.Favorite{})

	if result.Error != nil {
		return nil, result.Error
	}

	if result.RowsAffected == 0 {
		return nil, ErrNotFavorited
	}

	if err := database.DB.WithContext(ctx).
		Model(article).
		Update("favorites_count", gorm.Expr("GREATEST(favorites_count - 1, 0)")).Error; err != nil {
		return nil, err
	}

	if err := database.DB.WithContext(ctx).Preload("Author").First(article, article.ID).Error; err != nil {
		return nil, err
	}

	logging.Info(ctx).
		Uint("article_id", article.ID).
		Uint("user_id", userID).
		Msg("article unfavorited")

	return article, nil
}

func (s *ArticleService) IsFavorited(ctx context.Context, articleID, userID uint) bool {
	var count int64
	database.DB.WithContext(ctx).Model(&models.Favorite{}).
		Where("user_id = ? AND article_id = ?", userID, articleID).
		Count(&count)
	return count > 0
}

func generateSlug(title string) string {
	slug := strings.ToLower(title)
	reg := regexp.MustCompile(`[^a-z0-9]+`)
	slug = reg.ReplaceAllString(slug, "-")
	slug = strings.Trim(slug, "-")
	return slug
}
