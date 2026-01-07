use serde::{Deserialize, Serialize};
use sqlx::FromRow;
use time::OffsetDateTime;

#[derive(Debug, Clone, FromRow, Serialize)]
pub struct User {
    pub id: i32,
    pub email: String,
    #[serde(skip_serializing)]
    pub password_hash: String,
    pub name: String,
    pub bio: String,
    pub image: String,
    #[serde(with = "time::serde::rfc3339")]
    pub created_at: OffsetDateTime,
    #[serde(with = "time::serde::rfc3339")]
    pub updated_at: OffsetDateTime,
}

#[derive(Debug, Deserialize)]
pub struct RegisterInput {
    pub email: String,
    pub password: String,
    pub name: String,
}

#[derive(Debug, Deserialize)]
pub struct LoginInput {
    pub email: String,
    pub password: String,
}

#[derive(Debug, Serialize)]
pub struct UserResponse {
    pub user: UserWithToken,
}

#[derive(Debug, Serialize)]
pub struct UserWithToken {
    pub id: i32,
    pub email: String,
    pub name: String,
    pub bio: String,
    pub image: String,
    pub token: String,
}

impl UserWithToken {
    pub fn from_user(user: &User, token: String) -> Self {
        Self {
            id: user.id,
            email: user.email.clone(),
            name: user.name.clone(),
            bio: user.bio.clone(),
            image: user.image.clone(),
            token,
        }
    }
}

#[derive(Debug, Serialize)]
pub struct ProfileResponse {
    pub id: i32,
    pub email: String,
    pub name: String,
    pub bio: String,
    pub image: String,
}

impl From<User> for ProfileResponse {
    fn from(user: User) -> Self {
        Self {
            id: user.id,
            email: user.email,
            name: user.name,
            bio: user.bio,
            image: user.image,
        }
    }
}
