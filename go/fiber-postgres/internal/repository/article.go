package repository

import (
	"context"

	"github.com/jmoiron/sqlx"
	"go-fiber-postgres/internal/models"
)

type ArticleRepository struct {
	db *sqlx.DB
}

func NewArticleRepository(db *sqlx.DB) *ArticleRepository {
	return &ArticleRepository{db: db}
}

func (r *ArticleRepository) Create(ctx context.Context, article *models.Article) error {
	query := `
		INSERT INTO articles (slug, title, description, body, author_id)
		VALUES ($1, $2, $3, $4, $5)
		RETURNING id, favorites_count, created_at, updated_at`

	return r.db.QueryRowContext(ctx, query,
		article.Slug, article.Title, article.Description, article.Body, article.AuthorID,
	).Scan(&article.ID, &article.FavoritesCount, &article.CreatedAt, &article.UpdatedAt)
}

func (r *ArticleRepository) FindBySlug(ctx context.Context, slug string) (*models.Article, error) {
	query := `
		SELECT
			a.id, a.slug, a.title, a.description, a.body, a.author_id,
			a.favorites_count, a.created_at, a.updated_at,
			u.name as author_name, u.email as author_email, u.bio as author_bio, u.image as author_image
		FROM articles a
		JOIN users u ON a.author_id = u.id
		WHERE a.slug = $1`

	var row models.ArticleWithAuthor
	if err := r.db.GetContext(ctx, &row, query, slug); err != nil {
		return nil, err
	}
	return row.ToArticle(), nil
}

func (r *ArticleRepository) FindByID(ctx context.Context, id int) (*models.Article, error) {
	query := `
		SELECT
			a.id, a.slug, a.title, a.description, a.body, a.author_id,
			a.favorites_count, a.created_at, a.updated_at,
			u.name as author_name, u.email as author_email, u.bio as author_bio, u.image as author_image
		FROM articles a
		JOIN users u ON a.author_id = u.id
		WHERE a.id = $1`

	var row models.ArticleWithAuthor
	if err := r.db.GetContext(ctx, &row, query, id); err != nil {
		return nil, err
	}
	return row.ToArticle(), nil
}

func (r *ArticleRepository) List(ctx context.Context, limit, offset int) ([]*models.Article, error) {
	query := `
		SELECT
			a.id, a.slug, a.title, a.description, a.body, a.author_id,
			a.favorites_count, a.created_at, a.updated_at,
			u.name as author_name, u.email as author_email, u.bio as author_bio, u.image as author_image
		FROM articles a
		JOIN users u ON a.author_id = u.id
		ORDER BY a.created_at DESC
		LIMIT $1 OFFSET $2`

	var rows []models.ArticleWithAuthor
	if err := r.db.SelectContext(ctx, &rows, query, limit, offset); err != nil {
		return nil, err
	}

	articles := make([]*models.Article, len(rows))
	for i, row := range rows {
		articles[i] = row.ToArticle()
	}
	return articles, nil
}

func (r *ArticleRepository) Count(ctx context.Context) (int, error) {
	var count int
	query := `SELECT COUNT(*) FROM articles`

	if err := r.db.GetContext(ctx, &count, query); err != nil {
		return 0, err
	}
	return count, nil
}

func (r *ArticleRepository) Update(ctx context.Context, article *models.Article) error {
	query := `
		UPDATE articles SET title = $1, description = $2, body = $3, slug = $4, updated_at = NOW()
		WHERE id = $5
		RETURNING updated_at`

	return r.db.QueryRowContext(ctx, query,
		article.Title, article.Description, article.Body, article.Slug, article.ID,
	).Scan(&article.UpdatedAt)
}

func (r *ArticleRepository) Delete(ctx context.Context, id int) error {
	query := `DELETE FROM articles WHERE id = $1`
	_, err := r.db.ExecContext(ctx, query, id)
	return err
}

func (r *ArticleRepository) ExistsBySlug(ctx context.Context, slug string) (bool, error) {
	var exists bool
	query := `SELECT EXISTS(SELECT 1 FROM articles WHERE slug = $1)`

	if err := r.db.GetContext(ctx, &exists, query, slug); err != nil {
		return false, err
	}
	return exists, nil
}

func (r *ArticleRepository) IncrementFavorites(ctx context.Context, id int) error {
	query := `UPDATE articles SET favorites_count = favorites_count + 1 WHERE id = $1`
	_, err := r.db.ExecContext(ctx, query, id)
	return err
}

func (r *ArticleRepository) DecrementFavorites(ctx context.Context, id int) error {
	query := `UPDATE articles SET favorites_count = GREATEST(favorites_count - 1, 0) WHERE id = $1`
	_, err := r.db.ExecContext(ctx, query, id)
	return err
}
