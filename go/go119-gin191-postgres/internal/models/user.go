package models

import (
	"time"

	"github.com/google/uuid"
	"gorm.io/gorm"
)

type User struct {
	ID        uuid.UUID `gorm:"type:uuid;primary_key;default:gen_random_uuid()" json:"id"`
	Email     string    `gorm:"type:varchar(255);uniqueIndex;not null" json:"email" binding:"required,email"`
	Name      string    `gorm:"type:varchar(255);not null" json:"name" binding:"required"`
	Bio       string    `gorm:"type:text" json:"bio,omitempty"`
	Image     string    `gorm:"type:varchar(512)" json:"image,omitempty"`
	CreatedAt time.Time `json:"created_at"`
	UpdatedAt time.Time `json:"updated_at"`
}

// BeforeCreate will set a UUID rather than numeric ID.
func (u *User) BeforeCreate(tx *gorm.DB) error {
	if u.ID == uuid.Nil {
		u.ID = uuid.New()
	}
	return nil
}

// UserResponse is the JSON response structure
type UserResponse struct {
	User User `json:"user"`
}

// UsersResponse is the JSON response structure for multiple users
type UsersResponse struct {
	Users []User `json:"users"`
	Count int    `json:"count"`
}

// CreateUserRequest is the request payload for creating a user
type CreateUserRequest struct {
	Email string `json:"email" binding:"required,email"`
	Name  string `json:"name" binding:"required"`
	Bio   string `json:"bio,omitempty"`
	Image string `json:"image,omitempty"`
}

// UpdateUserRequest is the request payload for updating a user
type UpdateUserRequest struct {
	Name  *string `json:"name,omitempty"`
	Bio   *string `json:"bio,omitempty"`
	Image *string `json:"image,omitempty"`
}
