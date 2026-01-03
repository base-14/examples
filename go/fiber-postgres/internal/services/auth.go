package services

import (
	"context"
	"database/sql"
	"errors"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"go.opentelemetry.io/otel/codes"
	"golang.org/x/crypto/bcrypt"

	"go-fiber-postgres/internal/logging"
	"go-fiber-postgres/internal/models"
	"go-fiber-postgres/internal/repository"
	"go-fiber-postgres/internal/telemetry"
)

var (
	ErrInvalidCredentials = errors.New("invalid credentials")
	ErrEmailTaken         = errors.New("email already taken")
	ErrUserNotFound       = errors.New("user not found")
)

type AuthService struct {
	userRepo  *repository.UserRepository
	jwtSecret string
	jwtExpiry time.Duration
}

func NewAuthService(userRepo *repository.UserRepository, jwtSecret string, jwtExpiry time.Duration) *AuthService {
	return &AuthService{
		userRepo:  userRepo,
		jwtSecret: jwtSecret,
		jwtExpiry: jwtExpiry,
	}
}

type RegisterInput struct {
	Email    string `json:"email"`
	Password string `json:"password"`
	Name     string `json:"name"`
}

type LoginInput struct {
	Email    string `json:"email"`
	Password string `json:"password"`
}

type AuthResponse struct {
	User  models.UserResponse `json:"user"`
	Token string              `json:"token"`
}

func (s *AuthService) Register(ctx context.Context, input RegisterInput) (*AuthResponse, error) {
	ctx, span := telemetry.Tracer().Start(ctx, "user.register")
	defer span.End()

	exists, err := s.userRepo.ExistsByEmail(ctx, input.Email)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to check email")
		logging.Error(ctx, "failed to check email", "error", err)
		return nil, err
	}
	if exists {
		span.RecordError(ErrEmailTaken)
		span.SetStatus(codes.Error, ErrEmailTaken.Error())
		return nil, ErrEmailTaken
	}

	hashedPassword, err := bcrypt.GenerateFromPassword([]byte(input.Password), bcrypt.DefaultCost)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to hash password")
		logging.Error(ctx, "failed to hash password", "error", err)
		return nil, err
	}

	user := &models.User{
		Email:        input.Email,
		PasswordHash: string(hashedPassword),
		Name:         input.Name,
	}

	if err := s.userRepo.Create(ctx, user); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to create user")
		logging.Error(ctx, "failed to create user", "error", err)
		return nil, err
	}

	token, err := s.generateToken(user.ID)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to generate token")
		logging.Error(ctx, "failed to generate token", "error", err)
		return nil, err
	}

	span.SetStatus(codes.Ok, "user registered")
	logging.Info(ctx, "user registered", "userId", user.ID, "email", user.Email)

	return &AuthResponse{
		User:  user.ToResponse(),
		Token: token,
	}, nil
}

func (s *AuthService) Login(ctx context.Context, input LoginInput) (*AuthResponse, error) {
	ctx, span := telemetry.Tracer().Start(ctx, "user.login")
	defer span.End()

	user, err := s.userRepo.FindByEmail(ctx, input.Email)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			span.RecordError(ErrInvalidCredentials)
			span.SetStatus(codes.Error, ErrInvalidCredentials.Error())
			return nil, ErrInvalidCredentials
		}
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to find user")
		logging.Error(ctx, "failed to find user", "error", err)
		return nil, err
	}

	if err := bcrypt.CompareHashAndPassword([]byte(user.PasswordHash), []byte(input.Password)); err != nil {
		span.RecordError(ErrInvalidCredentials)
		span.SetStatus(codes.Error, ErrInvalidCredentials.Error())
		return nil, ErrInvalidCredentials
	}

	token, err := s.generateToken(user.ID)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to generate token")
		logging.Error(ctx, "failed to generate token", "error", err)
		return nil, err
	}

	span.SetStatus(codes.Ok, "user logged in")
	logging.Info(ctx, "user logged in", "userId", user.ID)

	return &AuthResponse{
		User:  user.ToResponse(),
		Token: token,
	}, nil
}

func (s *AuthService) GetUser(ctx context.Context, userID int) (*models.User, error) {
	user, err := s.userRepo.FindByID(ctx, userID)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, ErrUserNotFound
		}
		return nil, err
	}
	return user, nil
}

func (s *AuthService) generateToken(userID int) (string, error) {
	claims := jwt.MapClaims{
		"user_id": userID,
		"exp":     time.Now().Add(s.jwtExpiry).Unix(),
		"iat":     time.Now().Unix(),
	}

	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	return token.SignedString([]byte(s.jwtSecret))
}

func (s *AuthService) ValidateToken(tokenString string) (int, error) {
	token, err := jwt.Parse(tokenString, func(token *jwt.Token) (interface{}, error) {
		if _, ok := token.Method.(*jwt.SigningMethodHMAC); !ok {
			return nil, errors.New("unexpected signing method")
		}
		return []byte(s.jwtSecret), nil
	})

	if err != nil {
		return 0, err
	}

	if claims, ok := token.Claims.(jwt.MapClaims); ok && token.Valid {
		userID := int(claims["user_id"].(float64))
		return userID, nil
	}

	return 0, errors.New("invalid token")
}
