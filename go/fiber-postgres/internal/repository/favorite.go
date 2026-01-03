package repository

import (
	"context"
	"database/sql"
	"errors"

	"github.com/jmoiron/sqlx"
	"go-fiber-postgres/internal/models"
)

type FavoriteRepository struct {
	db *sqlx.DB
}

func NewFavoriteRepository(db *sqlx.DB) *FavoriteRepository {
	return &FavoriteRepository{db: db}
}

func (r *FavoriteRepository) Create(ctx context.Context, favorite *models.Favorite) error {
	query := `
		INSERT INTO favorites (user_id, article_id)
		VALUES ($1, $2)
		RETURNING id, created_at`

	return r.db.QueryRowContext(ctx, query,
		favorite.UserID, favorite.ArticleID,
	).Scan(&favorite.ID, &favorite.CreatedAt)
}

func (r *FavoriteRepository) Delete(ctx context.Context, userID, articleID int) error {
	query := `DELETE FROM favorites WHERE user_id = $1 AND article_id = $2`
	result, err := r.db.ExecContext(ctx, query, userID, articleID)
	if err != nil {
		return err
	}

	rows, err := result.RowsAffected()
	if err != nil {
		return err
	}
	if rows == 0 {
		return sql.ErrNoRows
	}
	return nil
}

func (r *FavoriteRepository) Exists(ctx context.Context, userID, articleID int) (bool, error) {
	var exists bool
	query := `SELECT EXISTS(SELECT 1 FROM favorites WHERE user_id = $1 AND article_id = $2)`

	if err := r.db.GetContext(ctx, &exists, query, userID, articleID); err != nil {
		return false, err
	}
	return exists, nil
}

func (r *FavoriteRepository) FindByUserID(ctx context.Context, userID int) ([]int, error) {
	var articleIDs []int
	query := `SELECT article_id FROM favorites WHERE user_id = $1`

	if err := r.db.SelectContext(ctx, &articleIDs, query, userID); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return []int{}, nil
		}
		return nil, err
	}
	return articleIDs, nil
}
