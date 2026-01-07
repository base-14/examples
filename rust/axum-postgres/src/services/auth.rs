use argon2::{
    password_hash::{rand_core::OsRng, PasswordHash, PasswordHasher, PasswordVerifier, SaltString},
    Argon2,
};
use jsonwebtoken::{decode, encode, DecodingKey, EncodingKey, Header, Validation};
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
        let parsed_hash =
            PasswordHash::new(hash).map_err(|e| AppError::Internal(format!("Invalid hash: {}", e)))?;

        Argon2::default()
            .verify_password(password.as_bytes(), &parsed_hash)
            .map_err(|_| AppError::InvalidCredentials)
    }
}
