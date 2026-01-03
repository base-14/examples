package models

import "time"

type Favorite struct {
	ID        int       `db:"id" json:"id"`
	UserID    int       `db:"user_id" json:"user_id"`
	ArticleID int       `db:"article_id" json:"article_id"`
	CreatedAt time.Time `db:"created_at" json:"created_at"`
}
