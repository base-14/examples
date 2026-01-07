use serde::{Deserialize, Serialize};
use sqlx::FromRow;
use time::OffsetDateTime;

use super::ProfileResponse;

#[derive(Debug, Clone, FromRow)]
pub struct Article {
    pub id: i32,
    pub slug: String,
    pub title: String,
    pub description: String,
    pub body: String,
    pub author_id: i32,
    pub favorites_count: i32,
    pub created_at: OffsetDateTime,
    pub updated_at: OffsetDateTime,
}

#[derive(Debug, Clone, FromRow)]
pub struct ArticleWithAuthor {
    pub id: i32,
    pub slug: String,
    pub title: String,
    pub description: String,
    pub body: String,
    pub author_id: i32,
    pub favorites_count: i32,
    pub created_at: OffsetDateTime,
    pub updated_at: OffsetDateTime,
    pub author_name: String,
    pub author_email: String,
    pub author_bio: String,
    pub author_image: String,
}

#[derive(Debug, Serialize)]
pub struct ArticleResponse {
    pub article: ArticleDto,
}

#[derive(Debug, Serialize)]
pub struct ArticlesResponse {
    pub articles: Vec<ArticleDto>,
    pub total: i64,
}

#[derive(Debug, Serialize)]
pub struct ArticleDto {
    pub id: i32,
    pub slug: String,
    pub title: String,
    pub description: String,
    pub body: String,
    pub favorites_count: i32,
    pub favorited: bool,
    #[serde(with = "time::serde::rfc3339")]
    pub created_at: OffsetDateTime,
    #[serde(with = "time::serde::rfc3339")]
    pub updated_at: OffsetDateTime,
    pub author: ProfileResponse,
}

impl ArticleDto {
    pub fn from_article_with_author(article: ArticleWithAuthor, favorited: bool) -> Self {
        Self {
            id: article.id,
            slug: article.slug,
            title: article.title,
            description: article.description,
            body: article.body,
            favorites_count: article.favorites_count,
            favorited,
            created_at: article.created_at,
            updated_at: article.updated_at,
            author: ProfileResponse {
                id: article.author_id,
                email: article.author_email,
                name: article.author_name,
                bio: article.author_bio,
                image: article.author_image,
            },
        }
    }
}

#[derive(Debug, Deserialize)]
pub struct CreateArticleInput {
    pub title: String,
    pub description: Option<String>,
    pub body: String,
}

#[derive(Debug, Deserialize)]
pub struct UpdateArticleInput {
    pub title: Option<String>,
    pub description: Option<String>,
    pub body: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct ListArticlesQuery {
    #[serde(default = "default_limit")]
    pub limit: i64,
    #[serde(default)]
    pub offset: i64,
    pub author: Option<String>,
}

fn default_limit() -> i64 {
    20
}
