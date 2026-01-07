use sqlx::{PgPool, Row};
use tracing::instrument;

use crate::models::{Article, ArticleWithAuthor};

#[derive(Clone)]
pub struct ArticleRepository {
    pool: PgPool,
}

impl ArticleRepository {
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }

    #[instrument(name = "db.article.create", skip(self))]
    pub async fn create(
        &self,
        slug: &str,
        title: &str,
        description: &str,
        body: &str,
        author_id: i32,
    ) -> Result<Article, sqlx::Error> {
        sqlx::query_as::<_, Article>(
            r#"
            INSERT INTO articles (slug, title, description, body, author_id)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id, slug, title, description, body, author_id, favorites_count, created_at, updated_at
            "#,
        )
        .bind(slug)
        .bind(title)
        .bind(description)
        .bind(body)
        .bind(author_id)
        .fetch_one(&self.pool)
        .await
    }

    #[instrument(name = "db.article.find_by_slug", skip(self))]
    pub async fn find_by_slug(&self, slug: &str) -> Result<Option<ArticleWithAuthor>, sqlx::Error> {
        sqlx::query_as::<_, ArticleWithAuthor>(
            r#"
            SELECT
                a.id, a.slug, a.title, a.description, a.body, a.author_id,
                a.favorites_count, a.created_at, a.updated_at,
                u.name as author_name, u.email as author_email,
                u.bio as author_bio, u.image as author_image
            FROM articles a
            JOIN users u ON a.author_id = u.id
            WHERE a.slug = $1
            "#,
        )
        .bind(slug)
        .fetch_optional(&self.pool)
        .await
    }

    #[instrument(name = "db.article.find_by_id", skip(self))]
    pub async fn find_by_id(&self, id: i32) -> Result<Option<ArticleWithAuthor>, sqlx::Error> {
        sqlx::query_as::<_, ArticleWithAuthor>(
            r#"
            SELECT
                a.id, a.slug, a.title, a.description, a.body, a.author_id,
                a.favorites_count, a.created_at, a.updated_at,
                u.name as author_name, u.email as author_email,
                u.bio as author_bio, u.image as author_image
            FROM articles a
            JOIN users u ON a.author_id = u.id
            WHERE a.id = $1
            "#,
        )
        .bind(id)
        .fetch_optional(&self.pool)
        .await
    }

    #[instrument(name = "db.article.list", skip(self))]
    pub async fn list(
        &self,
        limit: i64,
        offset: i64,
        author_name: Option<&str>,
    ) -> Result<Vec<ArticleWithAuthor>, sqlx::Error> {
        if let Some(author) = author_name {
            sqlx::query_as::<_, ArticleWithAuthor>(
                r#"
                SELECT
                    a.id, a.slug, a.title, a.description, a.body, a.author_id,
                    a.favorites_count, a.created_at, a.updated_at,
                    u.name as author_name, u.email as author_email,
                    u.bio as author_bio, u.image as author_image
                FROM articles a
                JOIN users u ON a.author_id = u.id
                WHERE u.name = $1
                ORDER BY a.created_at DESC
                LIMIT $2 OFFSET $3
                "#,
            )
            .bind(author)
            .bind(limit)
            .bind(offset)
            .fetch_all(&self.pool)
            .await
        } else {
            sqlx::query_as::<_, ArticleWithAuthor>(
                r#"
                SELECT
                    a.id, a.slug, a.title, a.description, a.body, a.author_id,
                    a.favorites_count, a.created_at, a.updated_at,
                    u.name as author_name, u.email as author_email,
                    u.bio as author_bio, u.image as author_image
                FROM articles a
                JOIN users u ON a.author_id = u.id
                ORDER BY a.created_at DESC
                LIMIT $1 OFFSET $2
                "#,
            )
            .bind(limit)
            .bind(offset)
            .fetch_all(&self.pool)
            .await
        }
    }

    #[instrument(name = "db.article.count", skip(self))]
    pub async fn count(&self, author_name: Option<&str>) -> Result<i64, sqlx::Error> {
        let row = if let Some(author) = author_name {
            sqlx::query(
                r#"
                SELECT COUNT(*) as count
                FROM articles a
                JOIN users u ON a.author_id = u.id
                WHERE u.name = $1
                "#,
            )
            .bind(author)
            .fetch_one(&self.pool)
            .await?
        } else {
            sqlx::query("SELECT COUNT(*) as count FROM articles")
                .fetch_one(&self.pool)
                .await?
        };

        Ok(row.get::<i64, _>("count"))
    }

    #[instrument(name = "db.article.update", skip(self))]
    pub async fn update(
        &self,
        id: i32,
        slug: Option<&str>,
        title: Option<&str>,
        description: Option<&str>,
        body: Option<&str>,
    ) -> Result<Article, sqlx::Error> {
        sqlx::query_as::<_, Article>(
            r#"
            UPDATE articles
            SET
                slug = COALESCE($2, slug),
                title = COALESCE($3, title),
                description = COALESCE($4, description),
                body = COALESCE($5, body)
            WHERE id = $1
            RETURNING id, slug, title, description, body, author_id, favorites_count, created_at, updated_at
            "#,
        )
        .bind(id)
        .bind(slug)
        .bind(title)
        .bind(description)
        .bind(body)
        .fetch_one(&self.pool)
        .await
    }

    #[instrument(name = "db.article.delete", skip(self))]
    pub async fn delete(&self, id: i32) -> Result<(), sqlx::Error> {
        sqlx::query("DELETE FROM articles WHERE id = $1")
            .bind(id)
            .execute(&self.pool)
            .await?;
        Ok(())
    }

    #[instrument(name = "db.article.exists_by_slug", skip(self))]
    pub async fn exists_by_slug(&self, slug: &str) -> Result<bool, sqlx::Error> {
        let row = sqlx::query("SELECT EXISTS(SELECT 1 FROM articles WHERE slug = $1) as exists")
            .bind(slug)
            .fetch_one(&self.pool)
            .await?;

        Ok(row.get::<bool, _>("exists"))
    }

    #[instrument(name = "db.article.increment_favorites", skip(self))]
    pub async fn increment_favorites(&self, id: i32) -> Result<(), sqlx::Error> {
        sqlx::query("UPDATE articles SET favorites_count = favorites_count + 1 WHERE id = $1")
            .bind(id)
            .execute(&self.pool)
            .await?;
        Ok(())
    }

    #[instrument(name = "db.article.decrement_favorites", skip(self))]
    pub async fn decrement_favorites(&self, id: i32) -> Result<(), sqlx::Error> {
        sqlx::query(
            "UPDATE articles SET favorites_count = GREATEST(favorites_count - 1, 0) WHERE id = $1",
        )
        .bind(id)
        .execute(&self.pool)
        .await?;
        Ok(())
    }
}
