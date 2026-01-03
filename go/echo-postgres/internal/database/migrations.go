package database

import (
	"go-echo-postgres/internal/models"
)

func Migrate() error {
	return DB.AutoMigrate(
		&models.User{},
		&models.Article{},
		&models.Favorite{},
	)
}
