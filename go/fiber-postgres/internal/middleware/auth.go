package middleware

import (
	"strings"

	"github.com/gofiber/fiber/v2"
	"go-fiber-postgres/internal/services"
)

type AuthMiddleware struct {
	authService *services.AuthService
}

func NewAuthMiddleware(authService *services.AuthService) *AuthMiddleware {
	return &AuthMiddleware{authService: authService}
}

func (m *AuthMiddleware) Required() fiber.Handler {
	return func(c *fiber.Ctx) error {
		authHeader := c.Get("Authorization")
		if authHeader == "" {
			return ErrorResponse(c, fiber.StatusUnauthorized, "missing authorization header")
		}

		parts := strings.Split(authHeader, " ")
		if len(parts) != 2 || strings.ToLower(parts[0]) != "bearer" {
			return ErrorResponse(c, fiber.StatusUnauthorized, "invalid authorization header format")
		}

		userID, err := m.authService.ValidateToken(parts[1])
		if err != nil {
			return ErrorResponse(c, fiber.StatusUnauthorized, "invalid or expired token")
		}

		c.Locals("userID", userID)
		return c.Next()
	}
}

func (m *AuthMiddleware) Optional() fiber.Handler {
	return func(c *fiber.Ctx) error {
		authHeader := c.Get("Authorization")
		if authHeader == "" {
			return c.Next()
		}

		parts := strings.Split(authHeader, " ")
		if len(parts) != 2 || strings.ToLower(parts[0]) != "bearer" {
			return c.Next()
		}

		userID, err := m.authService.ValidateToken(parts[1])
		if err == nil {
			c.Locals("userID", userID)
		}

		return c.Next()
	}
}

func GetUserID(c *fiber.Ctx) int {
	userID, ok := c.Locals("userID").(int)
	if !ok {
		return 0
	}
	return userID
}

func GetUserIDPtr(c *fiber.Ctx) *int {
	userID, ok := c.Locals("userID").(int)
	if !ok {
		return nil
	}
	return &userID
}
