package database

import (
	"errors"

	"github.com/base-14/examples/go/go-temporal-postgres/internal/models"
	"gorm.io/gorm"
)

func Migrate(db *gorm.DB) error {
	return db.AutoMigrate(
		&models.Product{},
		&models.Order{},
		&models.OrderItem{},
	)
}

func Seed(db *gorm.DB) error {
	products := []models.Product{
		{SKU: "prod-1", Name: "Widget A", Description: "Standard widget", Price: 29.99, Stock: 100},
		{SKU: "prod-2", Name: "Widget B", Description: "Premium widget", Price: 49.99, Stock: 50},
		{SKU: "prod-3", Name: "Widget C", Description: "Enterprise widget", Price: 99.99, Stock: 25},
		{SKU: "out-of-stock-item", Name: "Rare Widget", Description: "Very rare widget", Price: 199.99, Stock: 0},
	}

	for _, p := range products {
		var existing models.Product
		if err := db.Where("sku = ?", p.SKU).First(&existing).Error; errors.Is(err, gorm.ErrRecordNotFound) {
			if err := db.Create(&p).Error; err != nil {
				return err
			}
		}
	}

	return nil
}
