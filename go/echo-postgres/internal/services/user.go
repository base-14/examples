package services

import (
	"context"
	"errors"

	"go-echo-postgres/internal/database"
	"go-echo-postgres/internal/models"

	"go.opentelemetry.io/otel/attribute"
	"gorm.io/gorm"
)

type UserService struct{}

func NewUserService() *UserService {
	return &UserService{}
}

func (s *UserService) GetByID(ctx context.Context, userID uint) (*models.User, error) {
	ctx, span := tracer.Start(ctx, "user.get_by_id")
	defer span.End()

	span.SetAttributes(attribute.Int64("user.id", int64(userID)))

	var user models.User
	if err := database.DB.WithContext(ctx).First(&user, userID).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, ErrUserNotFound
		}
		return nil, err
	}

	return &user, nil
}

func (s *UserService) GetByEmail(ctx context.Context, email string) (*models.User, error) {
	ctx, span := tracer.Start(ctx, "user.get_by_email")
	defer span.End()

	span.SetAttributes(attribute.String("user.email", email))

	var user models.User
	if err := database.DB.WithContext(ctx).Where("email = ?", email).First(&user).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, ErrUserNotFound
		}
		return nil, err
	}

	return &user, nil
}

type UpdateUserInput struct {
	Name  *string `json:"name"`
	Bio   *string `json:"bio"`
	Image *string `json:"image"`
}

func (s *UserService) Update(ctx context.Context, userID uint, input UpdateUserInput) (*models.User, error) {
	ctx, span := tracer.Start(ctx, "user.update")
	defer span.End()

	span.SetAttributes(attribute.Int64("user.id", int64(userID)))

	var user models.User
	if err := database.DB.WithContext(ctx).First(&user, userID).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, ErrUserNotFound
		}
		return nil, err
	}

	updates := make(map[string]interface{})
	if input.Name != nil {
		updates["name"] = *input.Name
	}
	if input.Bio != nil {
		updates["bio"] = *input.Bio
	}
	if input.Image != nil {
		updates["image"] = *input.Image
	}

	if len(updates) > 0 {
		if err := database.DB.WithContext(ctx).Model(&user).Updates(updates).Error; err != nil {
			return nil, err
		}
	}

	return &user, nil
}
