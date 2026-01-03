package models

import (
	"time"
)

type Favorite struct {
	ID        uint      `gorm:"primaryKey" json:"id"`
	UserID    uint      `gorm:"not null;uniqueIndex:idx_user_article" json:"user_id"`
	ArticleID uint      `gorm:"not null;uniqueIndex:idx_user_article" json:"article_id"`
	CreatedAt time.Time `gorm:"autoCreateTime" json:"created_at"`

	User    User    `gorm:"foreignKey:UserID" json:"-"`
	Article Article `gorm:"foreignKey:ArticleID" json:"-"`
}
