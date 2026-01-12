package handlers

import (
	"errors"
	"net/http"

	"github.com/google/uuid"
	"github.com/labstack/echo/v4"
	"gorm.io/gorm"

	"github.com/base-14/examples/go/go-temporal-postgres/internal/models"
)

type ProductHandler struct {
	db *gorm.DB
}

func NewProductHandler(db *gorm.DB) *ProductHandler {
	return &ProductHandler{db: db}
}

func (h *ProductHandler) List(c echo.Context) error {
	var products []models.Product
	if err := h.db.WithContext(c.Request().Context()).Find(&products).Error; err != nil {
		return echo.NewHTTPError(http.StatusInternalServerError, "failed to fetch products")
	}
	return c.JSON(http.StatusOK, map[string]interface{}{
		"products": products,
	})
}

func (h *ProductHandler) Get(c echo.Context) error {
	id := c.Param("id")
	var product models.Product

	query := h.db.WithContext(c.Request().Context())
	if parsedID, err := uuid.Parse(id); err == nil {
		query = query.Where("id = ?", parsedID)
	} else {
		query = query.Where("sku = ?", id)
	}

	if err := query.First(&product).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return echo.NewHTTPError(http.StatusNotFound, "product not found")
		}
		return echo.NewHTTPError(http.StatusInternalServerError, "failed to fetch product")
	}
	return c.JSON(http.StatusOK, map[string]interface{}{
		"product": product,
	})
}
