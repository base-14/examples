package database

import (
	"context"
	"log/slog"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/jmoiron/sqlx"
	"github.com/riverqueue/river/riverdriver/riverpgxv5"
	"github.com/riverqueue/river/rivermigrate"
)

var migrations = []string{
	`CREATE TABLE IF NOT EXISTS users (
		id SERIAL PRIMARY KEY,
		email VARCHAR(255) UNIQUE NOT NULL,
		password_hash VARCHAR(255) NOT NULL,
		name VARCHAR(255) NOT NULL,
		bio TEXT DEFAULT '',
		image VARCHAR(255) DEFAULT '',
		created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
		updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
	)`,

	`CREATE TABLE IF NOT EXISTS articles (
		id SERIAL PRIMARY KEY,
		slug VARCHAR(255) UNIQUE NOT NULL,
		title VARCHAR(255) NOT NULL,
		description TEXT DEFAULT '',
		body TEXT NOT NULL,
		author_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
		favorites_count INTEGER DEFAULT 0,
		created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
		updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
	)`,

	`CREATE INDEX IF NOT EXISTS idx_articles_author_id ON articles(author_id)`,
	`CREATE INDEX IF NOT EXISTS idx_articles_created_at ON articles(created_at DESC)`,

	`CREATE TABLE IF NOT EXISTS favorites (
		id SERIAL PRIMARY KEY,
		user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
		article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
		created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
		UNIQUE(user_id, article_id)
	)`,

	`CREATE INDEX IF NOT EXISTS idx_favorites_user_id ON favorites(user_id)`,
	`CREATE INDEX IF NOT EXISTS idx_favorites_article_id ON favorites(article_id)`,
}

func RunMigrations(ctx context.Context, db *sqlx.DB) error {
	for i, migration := range migrations {
		if _, err := db.ExecContext(ctx, migration); err != nil {
			slog.Error("migration failed", "index", i, "error", err)
			return err
		}
	}
	slog.Info("migrations completed", "count", len(migrations))
	return nil
}

func RunRiverMigrations(ctx context.Context, pool *pgxpool.Pool) error {
	migrator, err := rivermigrate.New(riverpgxv5.New(pool), nil)
	if err != nil {
		return err
	}

	_, err = migrator.Migrate(ctx, rivermigrate.DirectionUp, nil)
	if err != nil {
		return err
	}

	slog.Info("river migrations completed")
	return nil
}
