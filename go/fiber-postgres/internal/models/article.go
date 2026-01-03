package models

import "time"

type Article struct {
	ID             int       `db:"id" json:"id"`
	Slug           string    `db:"slug" json:"slug"`
	Title          string    `db:"title" json:"title"`
	Description    string    `db:"description" json:"description"`
	Body           string    `db:"body" json:"body"`
	AuthorID       int       `db:"author_id" json:"author_id"`
	FavoritesCount int       `db:"favorites_count" json:"favorites_count"`
	CreatedAt      time.Time `db:"created_at" json:"created_at"`
	UpdatedAt      time.Time `db:"updated_at" json:"updated_at"`

	Author    *User `db:"-" json:"author,omitempty"`
	Favorited bool  `db:"-" json:"favorited"`
}

type ArticleWithAuthor struct {
	ID             int       `db:"id"`
	Slug           string    `db:"slug"`
	Title          string    `db:"title"`
	Description    string    `db:"description"`
	Body           string    `db:"body"`
	AuthorID       int       `db:"author_id"`
	FavoritesCount int       `db:"favorites_count"`
	CreatedAt      time.Time `db:"created_at"`
	UpdatedAt      time.Time `db:"updated_at"`
	AuthorName     string    `db:"author_name"`
	AuthorEmail    string    `db:"author_email"`
	AuthorBio      string    `db:"author_bio"`
	AuthorImage    string    `db:"author_image"`
}

func (a *ArticleWithAuthor) ToArticle() *Article {
	return &Article{
		ID:             a.ID,
		Slug:           a.Slug,
		Title:          a.Title,
		Description:    a.Description,
		Body:           a.Body,
		AuthorID:       a.AuthorID,
		FavoritesCount: a.FavoritesCount,
		CreatedAt:      a.CreatedAt,
		UpdatedAt:      a.UpdatedAt,
		Author: &User{
			ID:    a.AuthorID,
			Name:  a.AuthorName,
			Email: a.AuthorEmail,
			Bio:   a.AuthorBio,
			Image: a.AuthorImage,
		},
	}
}
