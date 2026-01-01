package handlers

import (
	"errors"

	"github.com/gofiber/fiber/v2"
	"go-fiber-postgres/internal/middleware"
	"go-fiber-postgres/internal/services"
)

type AuthHandler struct {
	authService *services.AuthService
}

func NewAuthHandler(authService *services.AuthService) *AuthHandler {
	return &AuthHandler{authService: authService}
}

func (h *AuthHandler) Register(c *fiber.Ctx) error {
	var input services.RegisterInput
	if err := c.BodyParser(&input); err != nil {
		return middleware.ErrorResponse(c, fiber.StatusBadRequest, "invalid request body")
	}

	if input.Email == "" || input.Password == "" || input.Name == "" {
		return middleware.ErrorResponse(c, fiber.StatusBadRequest, "email, password, and name are required")
	}

	ctx := c.UserContext()
	response, err := h.authService.Register(ctx, input)
	if err != nil {
		if errors.Is(err, services.ErrEmailTaken) {
			return middleware.ErrorResponse(c, fiber.StatusConflict, "email already taken")
		}
		return middleware.ErrorResponse(c, fiber.StatusInternalServerError, "failed to register user")
	}

	return c.Status(fiber.StatusCreated).JSON(response)
}

func (h *AuthHandler) Login(c *fiber.Ctx) error {
	var input services.LoginInput
	if err := c.BodyParser(&input); err != nil {
		return middleware.ErrorResponse(c, fiber.StatusBadRequest, "invalid request body")
	}

	if input.Email == "" || input.Password == "" {
		return middleware.ErrorResponse(c, fiber.StatusBadRequest, "email and password are required")
	}

	ctx := c.UserContext()
	response, err := h.authService.Login(ctx, input)
	if err != nil {
		if errors.Is(err, services.ErrInvalidCredentials) {
			return middleware.ErrorResponse(c, fiber.StatusUnauthorized, "invalid email or password")
		}
		return middleware.ErrorResponse(c, fiber.StatusInternalServerError, "failed to login")
	}

	return c.JSON(response)
}

func (h *AuthHandler) GetUser(c *fiber.Ctx) error {
	userID := middleware.GetUserID(c)
	ctx := c.UserContext()

	user, err := h.authService.GetUser(ctx, userID)
	if err != nil {
		if errors.Is(err, services.ErrUserNotFound) {
			return middleware.ErrorResponse(c, fiber.StatusNotFound, "user not found")
		}
		return middleware.ErrorResponse(c, fiber.StatusInternalServerError, "failed to get user")
	}

	return c.JSON(fiber.Map{
		"user": user.ToResponse(),
	})
}

func (h *AuthHandler) Logout(c *fiber.Ctx) error {
	return c.JSON(fiber.Map{
		"message": "logged out successfully",
	})
}
