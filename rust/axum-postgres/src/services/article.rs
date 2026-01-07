use tracing::instrument;

use crate::{
    error::{AppError, AppResult},
    jobs::JobQueue,
    models::{
        ArticleDto, ArticleResponse, ArticlesResponse, CreateArticleInput, ListArticlesQuery,
        UpdateArticleInput,
    },
    repository::{ArticleRepository, FavoriteRepository},
    telemetry::{
        ARTICLES_CREATED, ARTICLES_DELETED, ARTICLES_UPDATED, FAVORITES_ADDED, FAVORITES_REMOVED,
    },
};

#[derive(Clone)]
pub struct ArticleService {
    article_repo: ArticleRepository,
    favorite_repo: FavoriteRepository,
    job_queue: JobQueue,
}

impl ArticleService {
    pub fn new(
        article_repo: ArticleRepository,
        favorite_repo: FavoriteRepository,
        job_queue: JobQueue,
    ) -> Self {
        Self {
            article_repo,
            favorite_repo,
            job_queue,
        }
    }

    #[instrument(name = "article.create", skip(self, input), fields(author_id))]
    pub async fn create(
        &self,
        author_id: i32,
        input: CreateArticleInput,
    ) -> AppResult<ArticleResponse> {
        let slug = self.generate_slug(&input.title);
        let final_slug = if self.article_repo.exists_by_slug(&slug).await? {
            format!(
                "{}-{}",
                slug,
                time::OffsetDateTime::now_utc().unix_timestamp()
            )
        } else {
            slug
        };

        let article = self
            .article_repo
            .create(
                &final_slug,
                &input.title,
                input.description.as_deref().unwrap_or(""),
                &input.body,
                author_id,
            )
            .await?;

        let article_with_author =
            self.article_repo
                .find_by_id(article.id)
                .await?
                .ok_or(AppError::Internal(
                    "Failed to fetch created article".to_string(),
                ))?;

        if let Err(e) = self
            .job_queue
            .enqueue_notification(article.id, &article.title)
            .await
        {
            tracing::warn!(article_id = article.id, error = %e, "Failed to enqueue notification");
        }

        ARTICLES_CREATED.add(1, &[]);

        tracing::info!(article_id = article.id, slug = %article.slug, "Article created");

        Ok(ArticleResponse {
            article: ArticleDto::from_article_with_author(article_with_author, false),
        })
    }

    #[instrument(name = "article.get", skip(self))]
    pub async fn get(&self, slug: &str, user_id: Option<i32>) -> AppResult<ArticleResponse> {
        let article = self
            .article_repo
            .find_by_slug(slug)
            .await?
            .ok_or(AppError::NotFound("Article not found".to_string()))?;

        let favorited = if let Some(uid) = user_id {
            self.favorite_repo.exists(uid, article.id).await?
        } else {
            false
        };

        Ok(ArticleResponse {
            article: ArticleDto::from_article_with_author(article, favorited),
        })
    }

    #[instrument(name = "article.list", skip(self))]
    pub async fn list(
        &self,
        query: ListArticlesQuery,
        user_id: Option<i32>,
    ) -> AppResult<ArticlesResponse> {
        let articles = self
            .article_repo
            .list(query.limit, query.offset, query.author.as_deref())
            .await?;

        let total = self.article_repo.count(query.author.as_deref()).await?;

        let article_ids: Vec<i32> = articles.iter().map(|a| a.id).collect();

        let favorited_ids = if let Some(uid) = user_id {
            self.favorite_repo
                .is_favorited_batch(uid, &article_ids)
                .await?
        } else {
            vec![]
        };

        let articles_dto: Vec<ArticleDto> = articles
            .into_iter()
            .map(|a| {
                let favorited = favorited_ids.contains(&a.id);
                ArticleDto::from_article_with_author(a, favorited)
            })
            .collect();

        Ok(ArticlesResponse {
            articles: articles_dto,
            total,
        })
    }

    #[instrument(name = "article.update", skip(self, input))]
    pub async fn update(
        &self,
        slug: &str,
        user_id: i32,
        input: UpdateArticleInput,
    ) -> AppResult<ArticleResponse> {
        let article = self
            .article_repo
            .find_by_slug(slug)
            .await?
            .ok_or(AppError::NotFound("Article not found".to_string()))?;

        if article.author_id != user_id {
            return Err(AppError::Forbidden);
        }

        let new_slug = input.title.as_ref().map(|t| self.generate_slug(t));

        self.article_repo
            .update(
                article.id,
                new_slug.as_deref(),
                input.title.as_deref(),
                input.description.as_deref(),
                input.body.as_deref(),
            )
            .await?;

        let updated_article =
            self.article_repo
                .find_by_id(article.id)
                .await?
                .ok_or(AppError::Internal(
                    "Failed to fetch updated article".to_string(),
                ))?;

        let favorited = self.favorite_repo.exists(user_id, article.id).await?;

        ARTICLES_UPDATED.add(1, &[]);

        tracing::info!(article_id = article.id, "Article updated");

        Ok(ArticleResponse {
            article: ArticleDto::from_article_with_author(updated_article, favorited),
        })
    }

    #[instrument(name = "article.delete", skip(self))]
    pub async fn delete(&self, slug: &str, user_id: i32) -> AppResult<()> {
        let article = self
            .article_repo
            .find_by_slug(slug)
            .await?
            .ok_or(AppError::NotFound("Article not found".to_string()))?;

        if article.author_id != user_id {
            return Err(AppError::Forbidden);
        }

        self.article_repo.delete(article.id).await?;

        ARTICLES_DELETED.add(1, &[]);

        tracing::info!(article_id = article.id, "Article deleted");

        Ok(())
    }

    #[instrument(name = "article.favorite", skip(self))]
    pub async fn favorite(&self, slug: &str, user_id: i32) -> AppResult<ArticleResponse> {
        let article = self
            .article_repo
            .find_by_slug(slug)
            .await?
            .ok_or(AppError::NotFound("Article not found".to_string()))?;

        let already_favorited = self.favorite_repo.exists(user_id, article.id).await?;

        if !already_favorited {
            self.favorite_repo.create(user_id, article.id).await?;
            self.article_repo.increment_favorites(article.id).await?;
            FAVORITES_ADDED.add(1, &[]);
            tracing::info!(article_id = article.id, user_id, "Article favorited");
        }

        let updated_article = self
            .article_repo
            .find_by_id(article.id)
            .await?
            .ok_or(AppError::Internal("Failed to fetch article".to_string()))?;

        Ok(ArticleResponse {
            article: ArticleDto::from_article_with_author(updated_article, true),
        })
    }

    #[instrument(name = "article.unfavorite", skip(self))]
    pub async fn unfavorite(&self, slug: &str, user_id: i32) -> AppResult<ArticleResponse> {
        let article = self
            .article_repo
            .find_by_slug(slug)
            .await?
            .ok_or(AppError::NotFound("Article not found".to_string()))?;

        let was_favorited = self.favorite_repo.delete(user_id, article.id).await?;

        if was_favorited {
            self.article_repo.decrement_favorites(article.id).await?;
            FAVORITES_REMOVED.add(1, &[]);
            tracing::info!(article_id = article.id, user_id, "Article unfavorited");
        }

        let updated_article = self
            .article_repo
            .find_by_id(article.id)
            .await?
            .ok_or(AppError::Internal("Failed to fetch article".to_string()))?;

        Ok(ArticleResponse {
            article: ArticleDto::from_article_with_author(updated_article, false),
        })
    }

    fn generate_slug(&self, title: &str) -> String {
        generate_slug(title)
    }
}

pub fn generate_slug(title: &str) -> String {
    title
        .to_lowercase()
        .chars()
        .map(|c| if c.is_alphanumeric() { c } else { '-' })
        .collect::<String>()
        .split('-')
        .filter(|s| !s.is_empty())
        .collect::<Vec<_>>()
        .join("-")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_generate_slug_simple() {
        assert_eq!(generate_slug("Hello World"), "hello-world");
    }

    #[test]
    fn test_generate_slug_with_special_chars() {
        assert_eq!(
            generate_slug("Hello, World! How are you?"),
            "hello-world-how-are-you"
        );
    }

    #[test]
    fn test_generate_slug_with_numbers() {
        assert_eq!(
            generate_slug("Top 10 Tips for 2024"),
            "top-10-tips-for-2024"
        );
    }

    #[test]
    fn test_generate_slug_with_multiple_spaces() {
        assert_eq!(
            generate_slug("Multiple   Spaces   Here"),
            "multiple-spaces-here"
        );
    }

    #[test]
    fn test_generate_slug_preserves_lowercase() {
        assert_eq!(generate_slug("UPPERCASE TITLE"), "uppercase-title");
    }

    #[test]
    fn test_generate_slug_handles_leading_trailing_special_chars() {
        assert_eq!(generate_slug("---Hello World---"), "hello-world");
    }

    #[test]
    fn test_generate_slug_empty_title() {
        assert_eq!(generate_slug(""), "");
    }

    #[test]
    fn test_generate_slug_only_special_chars() {
        assert_eq!(generate_slug("!@#$%^&*()"), "");
    }
}
