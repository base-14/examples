package handlers

import (
	"errors"
	"net/http"

	"go-echo-postgres/internal/middleware"
	"go-echo-postgres/internal/services"

	"github.com/labstack/echo/v4"
)

type AuthHandler struct {
	authService *services.AuthService
	userService *services.UserService
}

func NewAuthHandler(authService *services.AuthService, userService *services.UserService) *AuthHandler {
	return &AuthHandler{
		authService: authService,
		userService: userService,
	}
}

func (h *AuthHandler) Register(c echo.Context) error {
	ctx := c.Request().Context()

	var input services.RegisterInput
	if err := c.Bind(&input); err != nil {
		return echo.NewHTTPError(http.StatusBadRequest, "invalid request body")
	}

	if input.Email == "" || input.Password == "" || input.Name == "" {
		return echo.NewHTTPError(http.StatusBadRequest, "email, password, and name are required")
	}

	if len(input.Password) < 6 {
		return echo.NewHTTPError(http.StatusBadRequest, "password must be at least 6 characters")
	}

	result, err := h.authService.Register(ctx, input)
	if err != nil {
		if errors.Is(err, services.ErrUserExists) {
			return echo.NewHTTPError(http.StatusConflict, "user with this email already exists")
		}
		return echo.NewHTTPError(http.StatusInternalServerError, "failed to register user")
	}

	return c.JSON(http.StatusCreated, result)
}

func (h *AuthHandler) Login(c echo.Context) error {
	ctx := c.Request().Context()

	var input services.LoginInput
	if err := c.Bind(&input); err != nil {
		return echo.NewHTTPError(http.StatusBadRequest, "invalid request body")
	}

	if input.Email == "" || input.Password == "" {
		return echo.NewHTTPError(http.StatusBadRequest, "email and password are required")
	}

	result, err := h.authService.Login(ctx, input)
	if err != nil {
		if errors.Is(err, services.ErrInvalidCredentials) {
			return echo.NewHTTPError(http.StatusUnauthorized, "invalid email or password")
		}
		return echo.NewHTTPError(http.StatusInternalServerError, "failed to login")
	}

	return c.JSON(http.StatusOK, result)
}

func (h *AuthHandler) GetCurrentUser(c echo.Context) error {
	ctx := c.Request().Context()

	userID, ok := middleware.GetUserID(c)
	if !ok {
		return echo.NewHTTPError(http.StatusUnauthorized, "unauthorized")
	}

	user, err := h.userService.GetByID(ctx, userID)
	if err != nil {
		if errors.Is(err, services.ErrUserNotFound) {
			return echo.NewHTTPError(http.StatusNotFound, "user not found")
		}
		return echo.NewHTTPError(http.StatusInternalServerError, "failed to get user")
	}

	return c.JSON(http.StatusOK, map[string]interface{}{
		"user": user.ToResponse(),
	})
}

func (h *AuthHandler) Logout(c echo.Context) error {
	return c.JSON(http.StatusOK, map[string]string{
		"message": "logged out successfully",
	})
}
