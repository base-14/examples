use sqlx::{PgPool, Row};
use tracing::instrument;

use crate::models::User;

#[derive(Clone)]
pub struct UserRepository {
    pool: PgPool,
}

impl UserRepository {
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }

    #[instrument(name = "db.user.create", skip(self, password_hash))]
    pub async fn create(
        &self,
        email: &str,
        password_hash: &str,
        name: &str,
    ) -> Result<User, sqlx::Error> {
        sqlx::query_as::<_, User>(
            r#"
            INSERT INTO users (email, password_hash, name)
            VALUES ($1, $2, $3)
            RETURNING id, email, password_hash, name, bio, image, created_at, updated_at
            "#,
        )
        .bind(email)
        .bind(password_hash)
        .bind(name)
        .fetch_one(&self.pool)
        .await
    }

    #[instrument(name = "db.user.find_by_email", skip(self))]
    pub async fn find_by_email(&self, email: &str) -> Result<Option<User>, sqlx::Error> {
        sqlx::query_as::<_, User>(
            r#"
            SELECT id, email, password_hash, name, bio, image, created_at, updated_at
            FROM users
            WHERE email = $1
            "#,
        )
        .bind(email)
        .fetch_optional(&self.pool)
        .await
    }

    #[instrument(name = "db.user.find_by_id", skip(self))]
    pub async fn find_by_id(&self, id: i32) -> Result<Option<User>, sqlx::Error> {
        sqlx::query_as::<_, User>(
            r#"
            SELECT id, email, password_hash, name, bio, image, created_at, updated_at
            FROM users
            WHERE id = $1
            "#,
        )
        .bind(id)
        .fetch_optional(&self.pool)
        .await
    }

    #[instrument(name = "db.user.exists_by_email", skip(self))]
    pub async fn exists_by_email(&self, email: &str) -> Result<bool, sqlx::Error> {
        let row = sqlx::query("SELECT EXISTS(SELECT 1 FROM users WHERE email = $1) as exists")
            .bind(email)
            .fetch_one(&self.pool)
            .await?;

        Ok(row.get::<bool, _>("exists"))
    }
}
