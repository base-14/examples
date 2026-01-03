package models

import (
	"time"
)

type Article struct {
	ID             uint      `gorm:"primaryKey" json:"id"`
	Slug           string    `gorm:"uniqueIndex;not null" json:"slug"`
	Title          string    `gorm:"not null" json:"title"`
	Description    string    `json:"description"`
	Body           string    `gorm:"type:text" json:"body"`
	AuthorID       uint      `gorm:"not null" json:"author_id"`
	FavoritesCount int       `gorm:"default:0" json:"favorites_count"`
	CreatedAt      time.Time `gorm:"autoCreateTime" json:"created_at"`
	UpdatedAt      time.Time `gorm:"autoUpdateTime" json:"updated_at"`

	Author    User       `gorm:"foreignKey:AuthorID" json:"author,omitempty"`
	Favorites []Favorite `gorm:"foreignKey:ArticleID" json:"-"`
}

type ArticleResponse struct {
	ID             uint         `json:"id"`
	Slug           string       `json:"slug"`
	Title          string       `json:"title"`
	Description    string       `json:"description"`
	Body           string       `json:"body"`
	FavoritesCount int          `json:"favorites_count"`
	Favorited      bool         `json:"favorited"`
	Author         UserResponse `json:"author"`
	CreatedAt      time.Time    `json:"created_at"`
	UpdatedAt      time.Time    `json:"updated_at"`
}

func (a *Article) ToResponse(favorited bool) ArticleResponse {
	return ArticleResponse{
		ID:             a.ID,
		Slug:           a.Slug,
		Title:          a.Title,
		Description:    a.Description,
		Body:           a.Body,
		FavoritesCount: a.FavoritesCount,
		Favorited:      favorited,
		Author:         a.Author.ToResponse(),
		CreatedAt:      a.CreatedAt,
		UpdatedAt:      a.UpdatedAt,
	}
}

type ArticlesResponse struct {
	Articles   []ArticleResponse `json:"articles"`
	TotalCount int64             `json:"total_count"`
	Page       int               `json:"page"`
	PerPage    int               `json:"per_page"`
}
