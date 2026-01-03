package services

import (
	"context"
	"database/sql"
	"errors"
	"regexp"
	"strings"
	"time"

	"go.opentelemetry.io/otel/codes"

	"go-fiber-postgres/internal/logging"
	"go-fiber-postgres/internal/models"
	"go-fiber-postgres/internal/repository"
	"go-fiber-postgres/internal/telemetry"
)

var (
	ErrArticleNotFound  = errors.New("article not found")
	ErrNotAuthor        = errors.New("not the author of this article")
	ErrAlreadyFavorited = errors.New("article already favorited")
	ErrNotFavorited     = errors.New("article not favorited")
)

type ArticleService struct {
	articleRepo  *repository.ArticleRepository
	favoriteRepo *repository.FavoriteRepository
}

func NewArticleService(articleRepo *repository.ArticleRepository, favoriteRepo *repository.FavoriteRepository) *ArticleService {
	return &ArticleService{
		articleRepo:  articleRepo,
		favoriteRepo: favoriteRepo,
	}
}

type CreateArticleInput struct {
	Title       string `json:"title"`
	Description string `json:"description"`
	Body        string `json:"body"`
}

type UpdateArticleInput struct {
	Title       *string `json:"title,omitempty"`
	Description *string `json:"description,omitempty"`
	Body        *string `json:"body,omitempty"`
}

type ArticleListResult struct {
	Articles   []*models.Article `json:"articles"`
	TotalCount int               `json:"total_count"`
}

func (s *ArticleService) Create(ctx context.Context, authorID int, input CreateArticleInput) (*models.Article, error) {
	ctx, span := telemetry.Tracer().Start(ctx, "article.create")
	defer span.End()

	slug := generateSlug(input.Title)

	exists, err := s.articleRepo.ExistsBySlug(ctx, slug)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to check slug")
		logging.Error(ctx, "failed to check slug", "error", err)
		return nil, err
	}
	if exists {
		slug = slug + "-" + time.Now().Format("20060102150405")
	}

	article := &models.Article{
		Slug:        slug,
		Title:       input.Title,
		Description: input.Description,
		Body:        input.Body,
		AuthorID:    authorID,
	}

	if err := s.articleRepo.Create(ctx, article); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to create article")
		logging.Error(ctx, "failed to create article", "error", err)
		return nil, err
	}

	telemetry.ArticlesCreated.Add(ctx, 1)
	span.SetStatus(codes.Ok, "article created")
	logging.Info(ctx, "article created", "articleId", article.ID, "slug", slug)

	return s.articleRepo.FindByID(ctx, article.ID)
}

func (s *ArticleService) GetBySlug(ctx context.Context, slug string, userID *int) (*models.Article, error) {
	article, err := s.articleRepo.FindBySlug(ctx, slug)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, ErrArticleNotFound
		}
		return nil, err
	}

	if userID != nil {
		favorited, err := s.favoriteRepo.Exists(ctx, *userID, article.ID)
		if err == nil {
			article.Favorited = favorited
		}
	}

	return article, nil
}

func (s *ArticleService) List(ctx context.Context, limit, offset int, userID *int) (*ArticleListResult, error) {
	articles, err := s.articleRepo.List(ctx, limit, offset)
	if err != nil {
		return nil, err
	}

	count, err := s.articleRepo.Count(ctx)
	if err != nil {
		return nil, err
	}

	if userID != nil {
		favoriteIDs, err := s.favoriteRepo.FindByUserID(ctx, *userID)
		if err == nil {
			favoriteSet := make(map[int]bool)
			for _, id := range favoriteIDs {
				favoriteSet[id] = true
			}
			for _, article := range articles {
				article.Favorited = favoriteSet[article.ID]
			}
		}
	}

	return &ArticleListResult{
		Articles:   articles,
		TotalCount: count,
	}, nil
}

func (s *ArticleService) Update(ctx context.Context, slug string, userID int, input UpdateArticleInput) (*models.Article, error) {
	ctx, span := telemetry.Tracer().Start(ctx, "article.update")
	defer span.End()

	article, err := s.articleRepo.FindBySlug(ctx, slug)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			span.RecordError(ErrArticleNotFound)
			span.SetStatus(codes.Error, ErrArticleNotFound.Error())
			return nil, ErrArticleNotFound
		}
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to find article")
		return nil, err
	}

	if article.AuthorID != userID {
		span.RecordError(ErrNotAuthor)
		span.SetStatus(codes.Error, ErrNotAuthor.Error())
		return nil, ErrNotAuthor
	}

	if input.Title != nil {
		article.Title = *input.Title
		article.Slug = generateSlug(*input.Title)
	}
	if input.Description != nil {
		article.Description = *input.Description
	}
	if input.Body != nil {
		article.Body = *input.Body
	}

	if err := s.articleRepo.Update(ctx, article); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to update article")
		logging.Error(ctx, "failed to update article", "error", err)
		return nil, err
	}

	span.SetStatus(codes.Ok, "article updated")
	logging.Info(ctx, "article updated", "articleId", article.ID)

	return s.articleRepo.FindByID(ctx, article.ID)
}

func (s *ArticleService) Delete(ctx context.Context, slug string, userID int) error {
	ctx, span := telemetry.Tracer().Start(ctx, "article.delete")
	defer span.End()

	article, err := s.articleRepo.FindBySlug(ctx, slug)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			span.RecordError(ErrArticleNotFound)
			span.SetStatus(codes.Error, ErrArticleNotFound.Error())
			return ErrArticleNotFound
		}
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to find article")
		return err
	}

	if article.AuthorID != userID {
		span.RecordError(ErrNotAuthor)
		span.SetStatus(codes.Error, ErrNotAuthor.Error())
		return ErrNotAuthor
	}

	if err := s.articleRepo.Delete(ctx, article.ID); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to delete article")
		logging.Error(ctx, "failed to delete article", "error", err)
		return err
	}

	telemetry.ArticlesDeleted.Add(ctx, 1)
	span.SetStatus(codes.Ok, "article deleted")
	logging.Info(ctx, "article deleted", "articleId", article.ID)

	return nil
}

func (s *ArticleService) Favorite(ctx context.Context, slug string, userID int) (*models.Article, error) {
	ctx, span := telemetry.Tracer().Start(ctx, "article.favorite")
	defer span.End()

	article, err := s.articleRepo.FindBySlug(ctx, slug)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			span.RecordError(ErrArticleNotFound)
			span.SetStatus(codes.Error, ErrArticleNotFound.Error())
			return nil, ErrArticleNotFound
		}
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to find article")
		return nil, err
	}

	exists, err := s.favoriteRepo.Exists(ctx, userID, article.ID)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to check favorite")
		return nil, err
	}
	if exists {
		span.RecordError(ErrAlreadyFavorited)
		span.SetStatus(codes.Error, ErrAlreadyFavorited.Error())
		return nil, ErrAlreadyFavorited
	}

	favorite := &models.Favorite{
		UserID:    userID,
		ArticleID: article.ID,
	}

	if err := s.favoriteRepo.Create(ctx, favorite); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to create favorite")
		logging.Error(ctx, "failed to create favorite", "error", err)
		return nil, err
	}

	if err := s.articleRepo.IncrementFavorites(ctx, article.ID); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to increment favorites")
		logging.Error(ctx, "failed to increment favorites", "error", err)
		return nil, err
	}

	telemetry.FavoritesAdded.Add(ctx, 1)
	span.SetStatus(codes.Ok, "article favorited")
	logging.Info(ctx, "article favorited", "articleId", article.ID, "userId", userID)

	return s.articleRepo.FindByID(ctx, article.ID)
}

func (s *ArticleService) Unfavorite(ctx context.Context, slug string, userID int) (*models.Article, error) {
	ctx, span := telemetry.Tracer().Start(ctx, "article.unfavorite")
	defer span.End()

	article, err := s.articleRepo.FindBySlug(ctx, slug)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			span.RecordError(ErrArticleNotFound)
			span.SetStatus(codes.Error, ErrArticleNotFound.Error())
			return nil, ErrArticleNotFound
		}
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to find article")
		return nil, err
	}

	if err := s.favoriteRepo.Delete(ctx, userID, article.ID); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			span.RecordError(ErrNotFavorited)
			span.SetStatus(codes.Error, ErrNotFavorited.Error())
			return nil, ErrNotFavorited
		}
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to delete favorite")
		logging.Error(ctx, "failed to delete favorite", "error", err)
		return nil, err
	}

	if err := s.articleRepo.DecrementFavorites(ctx, article.ID); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to decrement favorites")
		logging.Error(ctx, "failed to decrement favorites", "error", err)
		return nil, err
	}

	telemetry.FavoritesRemoved.Add(ctx, 1)
	span.SetStatus(codes.Ok, "article unfavorited")
	logging.Info(ctx, "article unfavorited", "articleId", article.ID, "userId", userID)

	return s.articleRepo.FindByID(ctx, article.ID)
}

func generateSlug(title string) string {
	slug := strings.ToLower(title)
	reg := regexp.MustCompile(`[^a-z0-9]+`)
	slug = reg.ReplaceAllString(slug, "-")
	slug = strings.Trim(slug, "-")
	return slug
}
