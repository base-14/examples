package repository

import (
	"context"
	"errors"
	"time"

	"stdlib-articles/model"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

var ErrNotFound = errors.New("article not found")

type ArticleRepository struct {
	pool *pgxpool.Pool
}

func NewArticleRepository(pool *pgxpool.Pool) *ArticleRepository {
	return &ArticleRepository{pool: pool}
}

func (r *ArticleRepository) List(ctx context.Context, page, perPage int) ([]model.Article, int, error) {
	offset := (page - 1) * perPage

	var total int
	if err := r.pool.QueryRow(ctx, `SELECT COUNT(*) FROM articles`).Scan(&total); err != nil {
		return nil, 0, err
	}

	rows, err := r.pool.Query(ctx, `
		SELECT id, title, body, created_at, updated_at
		FROM articles
		ORDER BY id DESC
		LIMIT $1 OFFSET $2
	`, perPage, offset)
	if err != nil {
		return nil, 0, err
	}
	defer rows.Close()

	articles := make([]model.Article, 0)
	for rows.Next() {
		var a model.Article
		if err := rows.Scan(&a.ID, &a.Title, &a.Body, &a.CreatedAt, &a.UpdatedAt); err != nil {
			return nil, 0, err
		}
		articles = append(articles, a)
	}
	return articles, total, rows.Err()
}

func (r *ArticleRepository) GetByID(ctx context.Context, id int64) (*model.Article, error) {
	var a model.Article
	err := r.pool.QueryRow(ctx, `
		SELECT id, title, body, created_at, updated_at
		FROM articles WHERE id = $1
	`, id).Scan(&a.ID, &a.Title, &a.Body, &a.CreatedAt, &a.UpdatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, ErrNotFound
	}
	if err != nil {
		return nil, err
	}
	return &a, nil
}

func (r *ArticleRepository) Create(ctx context.Context, title, body string) (*model.Article, error) {
	var a model.Article
	err := r.pool.QueryRow(ctx, `
		INSERT INTO articles (title, body)
		VALUES ($1, $2)
		RETURNING id, title, body, created_at, updated_at
	`, title, body).Scan(&a.ID, &a.Title, &a.Body, &a.CreatedAt, &a.UpdatedAt)
	if err != nil {
		return nil, err
	}
	return &a, nil
}

func (r *ArticleRepository) Update(ctx context.Context, id int64, title, body *string) (*model.Article, error) {
	var a model.Article
	err := r.pool.QueryRow(ctx, `
		UPDATE articles
		SET title = COALESCE($2, title),
		    body = COALESCE($3, body),
		    updated_at = $4
		WHERE id = $1
		RETURNING id, title, body, created_at, updated_at
	`, id, title, body, time.Now()).Scan(&a.ID, &a.Title, &a.Body, &a.CreatedAt, &a.UpdatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, ErrNotFound
	}
	if err != nil {
		return nil, err
	}
	return &a, nil
}

func (r *ArticleRepository) Delete(ctx context.Context, id int64) error {
	tag, err := r.pool.Exec(ctx, `DELETE FROM articles WHERE id = $1`, id)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}
