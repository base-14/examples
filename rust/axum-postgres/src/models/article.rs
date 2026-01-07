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

#[cfg(test)]
mod tests {
    use super::*;
    use time::macros::datetime;

    fn create_test_article_with_author() -> ArticleWithAuthor {
        ArticleWithAuthor {
            id: 1,
            slug: "test-article".to_string(),
            title: "Test Article".to_string(),
            description: "A test description".to_string(),
            body: "The body of the article".to_string(),
            author_id: 42,
            favorites_count: 10,
            created_at: datetime!(2024-01-15 10:30:00 UTC),
            updated_at: datetime!(2024-01-16 15:45:00 UTC),
            author_name: "John Doe".to_string(),
            author_email: "john@example.com".to_string(),
            author_bio: "A test user".to_string(),
            author_image: "https://example.com/avatar.jpg".to_string(),
        }
    }

    #[test]
    fn test_article_dto_from_article_with_author() {
        let article = create_test_article_with_author();
        let dto = ArticleDto::from_article_with_author(article.clone(), true);

        assert_eq!(dto.id, article.id);
        assert_eq!(dto.slug, article.slug);
        assert_eq!(dto.title, article.title);
        assert_eq!(dto.description, article.description);
        assert_eq!(dto.body, article.body);
        assert_eq!(dto.favorites_count, article.favorites_count);
        assert!(dto.favorited);
        assert_eq!(dto.author.id, article.author_id);
        assert_eq!(dto.author.name, article.author_name);
        assert_eq!(dto.author.email, article.author_email);
    }

    #[test]
    fn test_article_dto_not_favorited() {
        let article = create_test_article_with_author();
        let dto = ArticleDto::from_article_with_author(article, false);

        assert!(!dto.favorited);
    }

    #[test]
    fn test_article_response_serialization() {
        let article = create_test_article_with_author();
        let dto = ArticleDto::from_article_with_author(article, true);
        let response = ArticleResponse { article: dto };

        let json = serde_json::to_string(&response).expect("serialization should succeed");
        assert!(json.contains("\"slug\":\"test-article\""));
        assert!(json.contains("\"favorited\":true"));
        assert!(json.contains("\"author\":{"));
    }

    #[test]
    fn test_articles_response_serialization() {
        let article = create_test_article_with_author();
        let dto = ArticleDto::from_article_with_author(article, false);
        let response = ArticlesResponse {
            articles: vec![dto],
            total: 1,
        };

        let json = serde_json::to_string(&response).expect("serialization should succeed");
        assert!(json.contains("\"articles\":["));
        assert!(json.contains("\"total\":1"));
    }

    #[test]
    fn test_create_article_input_deserialization() {
        let json =
            r#"{"title": "New Article", "description": "Description", "body": "Body content"}"#;
        let input: CreateArticleInput =
            serde_json::from_str(json).expect("deserialization should succeed");

        assert_eq!(input.title, "New Article");
        assert_eq!(input.description, Some("Description".to_string()));
        assert_eq!(input.body, "Body content");
    }

    #[test]
    fn test_create_article_input_without_description() {
        let json = r#"{"title": "New Article", "body": "Body content"}"#;
        let input: CreateArticleInput =
            serde_json::from_str(json).expect("deserialization should succeed");

        assert_eq!(input.title, "New Article");
        assert!(input.description.is_none());
        assert_eq!(input.body, "Body content");
    }

    #[test]
    fn test_update_article_input_partial() {
        let json = r#"{"title": "Updated Title"}"#;
        let input: UpdateArticleInput =
            serde_json::from_str(json).expect("deserialization should succeed");

        assert_eq!(input.title, Some("Updated Title".to_string()));
        assert!(input.description.is_none());
        assert!(input.body.is_none());
    }

    #[test]
    fn test_list_articles_query_defaults() {
        let json = r#"{}"#;
        let query: ListArticlesQuery =
            serde_json::from_str(json).expect("deserialization should succeed");

        assert_eq!(query.limit, 20);
        assert_eq!(query.offset, 0);
        assert!(query.author.is_none());
    }

    #[test]
    fn test_list_articles_query_with_params() {
        let json = r#"{"limit": 10, "offset": 5, "author": "john"}"#;
        let query: ListArticlesQuery =
            serde_json::from_str(json).expect("deserialization should succeed");

        assert_eq!(query.limit, 10);
        assert_eq!(query.offset, 5);
        assert_eq!(query.author, Some("john".to_string()));
    }
}
