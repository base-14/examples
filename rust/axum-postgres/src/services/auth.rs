use argon2::{
    Argon2,
    password_hash::{PasswordHash, PasswordHasher, PasswordVerifier, SaltString, rand_core::OsRng},
};
use jsonwebtoken::{DecodingKey, EncodingKey, Header, Validation, decode, encode};
use serde::{Deserialize, Serialize};
use time::{Duration, OffsetDateTime};
use tracing::instrument;

use crate::{
    config::Config,
    error::{AppError, AppResult},
    models::{LoginInput, RegisterInput, User, UserWithToken},
    repository::UserRepository,
    telemetry::USERS_REGISTERED,
};

#[derive(Debug, Serialize, Deserialize)]
pub struct Claims {
    pub sub: i32,
    pub exp: i64,
    pub iat: i64,
}

#[derive(Clone)]
pub struct AuthService {
    user_repo: UserRepository,
    jwt_secret: String,
    jwt_expires_in_hours: i64,
}

impl AuthService {
    pub fn new(user_repo: UserRepository, config: &Config) -> Self {
        Self {
            user_repo,
            jwt_secret: config.jwt_secret.clone(),
            jwt_expires_in_hours: config.jwt_expires_in_hours,
        }
    }

    #[instrument(name = "auth.register", skip(self, input), fields(email = %input.email))]
    pub async fn register(&self, input: RegisterInput) -> AppResult<UserWithToken> {
        if self.user_repo.exists_by_email(&input.email).await? {
            return Err(AppError::Conflict("Email already registered".to_string()));
        }

        let password_hash = self.hash_password(&input.password)?;

        let user = self
            .user_repo
            .create(&input.email, &password_hash, &input.name)
            .await?;

        let token = self.generate_token(user.id)?;

        USERS_REGISTERED.add(1, &[]);

        tracing::info!(user_id = user.id, "User registered");

        Ok(UserWithToken::from_user(&user, token))
    }

    #[instrument(name = "auth.login", skip(self, input), fields(email = %input.email))]
    pub async fn login(&self, input: LoginInput) -> AppResult<UserWithToken> {
        let user = self
            .user_repo
            .find_by_email(&input.email)
            .await?
            .ok_or(AppError::InvalidCredentials)?;

        self.verify_password(&input.password, &user.password_hash)?;

        let token = self.generate_token(user.id)?;

        tracing::info!(user_id = user.id, "User logged in");

        Ok(UserWithToken::from_user(&user, token))
    }

    #[instrument(name = "auth.get_user", skip(self))]
    pub async fn get_user(&self, user_id: i32) -> AppResult<User> {
        self.user_repo
            .find_by_id(user_id)
            .await?
            .ok_or(AppError::NotFound("User not found".to_string()))
    }

    #[instrument(name = "auth.validate_token", skip(self, token))]
    pub fn validate_token(&self, token: &str) -> AppResult<i32> {
        let token_data = decode::<Claims>(
            token,
            &DecodingKey::from_secret(self.jwt_secret.as_bytes()),
            &Validation::default(),
        )?;

        Ok(token_data.claims.sub)
    }

    fn generate_token(&self, user_id: i32) -> AppResult<String> {
        let now = OffsetDateTime::now_utc();
        let exp = now + Duration::hours(self.jwt_expires_in_hours);

        let claims = Claims {
            sub: user_id,
            exp: exp.unix_timestamp(),
            iat: now.unix_timestamp(),
        };

        let token = encode(
            &Header::default(),
            &claims,
            &EncodingKey::from_secret(self.jwt_secret.as_bytes()),
        )?;

        Ok(token)
    }

    fn hash_password(&self, password: &str) -> AppResult<String> {
        let salt = SaltString::generate(&mut OsRng);
        let argon2 = Argon2::default();

        argon2
            .hash_password(password.as_bytes(), &salt)
            .map(|hash| hash.to_string())
            .map_err(|e| AppError::Internal(format!("Password hashing failed: {}", e)))
    }

    fn verify_password(&self, password: &str, hash: &str) -> AppResult<()> {
        let parsed_hash = PasswordHash::new(hash)
            .map_err(|e| AppError::Internal(format!("Invalid hash: {}", e)))?;

        Argon2::default()
            .verify_password(password.as_bytes(), &parsed_hash)
            .map_err(|_| AppError::InvalidCredentials)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn create_test_claims(user_id: i32, hours_offset: i64) -> Claims {
        let now = OffsetDateTime::now_utc();
        let exp = now + Duration::hours(hours_offset);
        Claims {
            sub: user_id,
            exp: exp.unix_timestamp(),
            iat: now.unix_timestamp(),
        }
    }

    #[test]
    fn test_jwt_encode_decode() {
        let secret = "test-secret-key-for-jwt";
        let user_id = 42;

        let claims = create_test_claims(user_id, 24);

        let token = encode(
            &Header::default(),
            &claims,
            &EncodingKey::from_secret(secret.as_bytes()),
        )
        .expect("encoding should succeed");

        let decoded = decode::<Claims>(
            &token,
            &DecodingKey::from_secret(secret.as_bytes()),
            &Validation::default(),
        )
        .expect("decoding should succeed");

        assert_eq!(decoded.claims.sub, user_id);
    }

    #[test]
    fn test_jwt_expired_token() {
        let secret = "test-secret-key-for-jwt";
        let user_id = 42;

        let claims = create_test_claims(user_id, -1);

        let token = encode(
            &Header::default(),
            &claims,
            &EncodingKey::from_secret(secret.as_bytes()),
        )
        .expect("encoding should succeed");

        let result = decode::<Claims>(
            &token,
            &DecodingKey::from_secret(secret.as_bytes()),
            &Validation::default(),
        );

        assert!(result.is_err());
    }

    #[test]
    fn test_jwt_wrong_secret() {
        let secret = "test-secret-key-for-jwt";
        let wrong_secret = "wrong-secret";
        let user_id = 42;

        let claims = create_test_claims(user_id, 24);

        let token = encode(
            &Header::default(),
            &claims,
            &EncodingKey::from_secret(secret.as_bytes()),
        )
        .expect("encoding should succeed");

        let result = decode::<Claims>(
            &token,
            &DecodingKey::from_secret(wrong_secret.as_bytes()),
            &Validation::default(),
        );

        assert!(result.is_err());
    }

    #[test]
    fn test_password_hash_and_verify() {
        let password = "secure_password_123";
        let salt = SaltString::generate(&mut OsRng);
        let argon2 = Argon2::default();

        let hash = argon2
            .hash_password(password.as_bytes(), &salt)
            .expect("hashing should succeed")
            .to_string();

        let parsed_hash = PasswordHash::new(&hash).expect("parsing should succeed");

        let result = argon2.verify_password(password.as_bytes(), &parsed_hash);
        assert!(result.is_ok());
    }

    #[test]
    fn test_password_verify_wrong_password() {
        let password = "secure_password_123";
        let wrong_password = "wrong_password";
        let salt = SaltString::generate(&mut OsRng);
        let argon2 = Argon2::default();

        let hash = argon2
            .hash_password(password.as_bytes(), &salt)
            .expect("hashing should succeed")
            .to_string();

        let parsed_hash = PasswordHash::new(&hash).expect("parsing should succeed");

        let result = argon2.verify_password(wrong_password.as_bytes(), &parsed_hash);
        assert!(result.is_err());
    }

    #[test]
    fn test_claims_serialization() {
        let claims = create_test_claims(42, 24);
        let json = serde_json::to_string(&claims).expect("serialization should succeed");
        let parsed: Claims = serde_json::from_str(&json).expect("deserialization should succeed");

        assert_eq!(claims.sub, parsed.sub);
        assert_eq!(claims.exp, parsed.exp);
        assert_eq!(claims.iat, parsed.iat);
    }
}
