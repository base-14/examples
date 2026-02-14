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

#[cfg(test)]
mod tests {
    use super::*;
    use time::macros::datetime;

    fn create_test_user() -> User {
        User {
            id: 1,
            email: "test@example.com".to_string(),
            password_hash: "hashed_password".to_string(),
            name: "Test User".to_string(),
            bio: "A bio".to_string(),
            image: "https://example.com/avatar.jpg".to_string(),
            created_at: datetime!(2024-01-15 10:30:00 UTC),
            updated_at: datetime!(2024-01-16 15:45:00 UTC),
        }
    }

    #[test]
    fn test_user_with_token_from_user() {
        let user = create_test_user();
        let token = "jwt_token_here".to_string();

        let user_with_token = UserWithToken::from_user(&user, token.clone());

        assert_eq!(user_with_token.id, user.id);
        assert_eq!(user_with_token.email, user.email);
        assert_eq!(user_with_token.name, user.name);
        assert_eq!(user_with_token.bio, user.bio);
        assert_eq!(user_with_token.image, user.image);
        assert_eq!(user_with_token.token, token);
    }

    #[test]
    fn test_profile_response_from_user() {
        let user = create_test_user();
        let profile: ProfileResponse = user.clone().into();

        assert_eq!(profile.id, user.id);
        assert_eq!(profile.email, user.email);
        assert_eq!(profile.name, user.name);
        assert_eq!(profile.bio, user.bio);
        assert_eq!(profile.image, user.image);
    }

    #[test]
    fn test_user_serialization_excludes_password() {
        let user = create_test_user();
        let json = serde_json::to_string(&user).expect("serialization should succeed");

        assert!(json.contains("\"email\":\"test@example.com\""));
        assert!(json.contains("\"name\":\"Test User\""));
        assert!(!json.contains("password_hash"));
        assert!(!json.contains("hashed_password"));
    }

    #[test]
    fn test_register_input_deserialization() {
        let json = r#"{"email": "new@example.com", "password": "secret123", "name": "New User"}"#;
        let input: RegisterInput =
            serde_json::from_str(json).expect("deserialization should succeed");

        assert_eq!(input.email, "new@example.com");
        assert_eq!(input.password, "secret123");
        assert_eq!(input.name, "New User");
    }

    #[test]
    fn test_login_input_deserialization() {
        let json = r#"{"email": "test@example.com", "password": "secret123"}"#;
        let input: LoginInput = serde_json::from_str(json).expect("deserialization should succeed");

        assert_eq!(input.email, "test@example.com");
        assert_eq!(input.password, "secret123");
    }

    #[test]
    fn test_user_response_serialization() {
        let user = create_test_user();
        let user_with_token = UserWithToken::from_user(&user, "token".to_string());
        let response = UserResponse {
            user: user_with_token,
        };

        let json = serde_json::to_string(&response).expect("serialization should succeed");
        assert!(json.contains("\"user\":{"));
        assert!(json.contains("\"token\":\"token\""));
    }

    #[test]
    fn test_profile_response_serialization() {
        let user = create_test_user();
        let profile: ProfileResponse = user.into();

        let json = serde_json::to_string(&profile).expect("serialization should succeed");
        assert!(json.contains("\"id\":1"));
        assert!(json.contains("\"email\":\"test@example.com\""));
    }
}
