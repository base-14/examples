package repository

import (
	"context"

	"github.com/jmoiron/sqlx"
	"go-fiber-postgres/internal/models"
)

type UserRepository struct {
	db *sqlx.DB
}

func NewUserRepository(db *sqlx.DB) *UserRepository {
	return &UserRepository{db: db}
}

func (r *UserRepository) Create(ctx context.Context, user *models.User) error {
	query := `
		INSERT INTO users (email, password_hash, name, bio, image)
		VALUES ($1, $2, $3, $4, $5)
		RETURNING id, created_at, updated_at`

	return r.db.QueryRowContext(ctx, query,
		user.Email, user.PasswordHash, user.Name, user.Bio, user.Image,
	).Scan(&user.ID, &user.CreatedAt, &user.UpdatedAt)
}

func (r *UserRepository) FindByID(ctx context.Context, id int) (*models.User, error) {
	var user models.User
	query := `SELECT * FROM users WHERE id = $1`

	if err := r.db.GetContext(ctx, &user, query, id); err != nil {
		return nil, err
	}
	return &user, nil
}

func (r *UserRepository) FindByEmail(ctx context.Context, email string) (*models.User, error) {
	var user models.User
	query := `SELECT * FROM users WHERE email = $1`

	if err := r.db.GetContext(ctx, &user, query, email); err != nil {
		return nil, err
	}
	return &user, nil
}

func (r *UserRepository) Update(ctx context.Context, user *models.User) error {
	query := `
		UPDATE users SET name = $1, bio = $2, image = $3, updated_at = NOW()
		WHERE id = $4
		RETURNING updated_at`

	return r.db.QueryRowContext(ctx, query,
		user.Name, user.Bio, user.Image, user.ID,
	).Scan(&user.UpdatedAt)
}

func (r *UserRepository) ExistsByEmail(ctx context.Context, email string) (bool, error) {
	var exists bool
	query := `SELECT EXISTS(SELECT 1 FROM users WHERE email = $1)`

	if err := r.db.GetContext(ctx, &exists, query, email); err != nil {
		return false, err
	}
	return exists, nil
}
