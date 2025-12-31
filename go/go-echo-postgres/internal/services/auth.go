package services

import (
	"context"
	"errors"
	"time"

	"go-echo-postgres/internal/database"
	"go-echo-postgres/internal/logging"
	"go-echo-postgres/internal/middleware"
	"go-echo-postgres/internal/models"

	"github.com/golang-jwt/jwt/v5"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"
	"golang.org/x/crypto/bcrypt"
	"gorm.io/gorm"
)

var (
	tracer              = otel.Tracer("go-echo-postgres")
	meter               = otel.Meter("go-echo-postgres")
	registrationCounter metric.Int64Counter
	loginCounter        metric.Int64Counter
)

var (
	ErrUserExists       = errors.New("user already exists")
	ErrInvalidCredentials = errors.New("invalid credentials")
	ErrUserNotFound     = errors.New("user not found")
)

type AuthService struct {
	jwtSecret    string
	jwtExpiresIn time.Duration
}

func NewAuthService(jwtSecret string, jwtExpiresIn time.Duration) *AuthService {
	var err error
	registrationCounter, err = meter.Int64Counter(
		"auth.registration.total",
		metric.WithDescription("Total number of user registrations"),
	)
	if err != nil {
		logging.Logger().Error().Err(err).Msg("failed to create registration counter")
	}

	loginCounter, err = meter.Int64Counter(
		"auth.login.attempts",
		metric.WithDescription("Total number of login attempts"),
	)
	if err != nil {
		logging.Logger().Error().Err(err).Msg("failed to create login counter")
	}

	return &AuthService{
		jwtSecret:    jwtSecret,
		jwtExpiresIn: jwtExpiresIn,
	}
}

type RegisterInput struct {
	Email    string `json:"email" validate:"required,email"`
	Password string `json:"password" validate:"required,min=6"`
	Name     string `json:"name" validate:"required"`
}

type LoginInput struct {
	Email    string `json:"email" validate:"required,email"`
	Password string `json:"password" validate:"required"`
}

type AuthResponse struct {
	User  models.UserResponse `json:"user"`
	Token string              `json:"token"`
}

func (s *AuthService) Register(ctx context.Context, input RegisterInput) (*AuthResponse, error) {
	ctx, span := tracer.Start(ctx, "user.register")
	defer span.End()

	span.SetAttributes(attribute.String("user.email", input.Email))

	var existingUser models.User
	if err := database.DB.WithContext(ctx).Where("email = ?", input.Email).First(&existingUser).Error; err == nil {
		span.SetAttributes(attribute.Bool("user.exists", true))
		return nil, ErrUserExists
	} else if !errors.Is(err, gorm.ErrRecordNotFound) {
		return nil, err
	}

	hashedPassword, err := bcrypt.GenerateFromPassword([]byte(input.Password), bcrypt.DefaultCost)
	if err != nil {
		return nil, err
	}

	user := models.User{
		Email:        input.Email,
		PasswordHash: string(hashedPassword),
		Name:         input.Name,
	}

	if err := database.DB.WithContext(ctx).Create(&user).Error; err != nil {
		return nil, err
	}

	if registrationCounter != nil {
		registrationCounter.Add(ctx, 1, metric.WithAttributes(
			attribute.Bool("success", true),
		))
	}

	token, err := s.generateToken(&user)
	if err != nil {
		return nil, err
	}

	span.SetAttributes(
		attribute.Int64("user.id", int64(user.ID)),
		attribute.Bool("registration.success", true),
	)

	logging.Info(ctx).
		Uint("user_id", user.ID).
		Str("email", user.Email).
		Msg("user registered successfully")

	return &AuthResponse{
		User:  user.ToResponse(),
		Token: token,
	}, nil
}

func (s *AuthService) Login(ctx context.Context, input LoginInput) (*AuthResponse, error) {
	ctx, span := tracer.Start(ctx, "user.login")
	defer span.End()

	span.SetAttributes(attribute.String("user.email", input.Email))

	if loginCounter != nil {
		loginCounter.Add(ctx, 1)
	}

	var user models.User
	if err := database.DB.WithContext(ctx).Where("email = ?", input.Email).First(&user).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			span.SetAttributes(attribute.Bool("login.success", false))
			return nil, ErrInvalidCredentials
		}
		return nil, err
	}

	if err := bcrypt.CompareHashAndPassword([]byte(user.PasswordHash), []byte(input.Password)); err != nil {
		span.SetAttributes(attribute.Bool("login.success", false))
		return nil, ErrInvalidCredentials
	}

	token, err := s.generateToken(&user)
	if err != nil {
		return nil, err
	}

	span.SetAttributes(
		attribute.Int64("user.id", int64(user.ID)),
		attribute.Bool("login.success", true),
	)

	logging.Info(ctx).
		Uint("user_id", user.ID).
		Str("email", user.Email).
		Msg("user logged in successfully")

	return &AuthResponse{
		User:  user.ToResponse(),
		Token: token,
	}, nil
}

func (s *AuthService) generateToken(user *models.User) (string, error) {
	claims := middleware.JWTClaims{
		UserID: user.ID,
		Email:  user.Email,
		RegisteredClaims: jwt.RegisteredClaims{
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(s.jwtExpiresIn)),
			IssuedAt:  jwt.NewNumericDate(time.Now()),
		},
	}

	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	return token.SignedString([]byte(s.jwtSecret))
}
