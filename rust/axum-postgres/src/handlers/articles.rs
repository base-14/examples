use axum::{
    extract::{Path, Query, State},
    http::StatusCode,
    Json,
};

use crate::{
    error::AppResult,
    middleware::{AuthUser, OptionalAuthUser},
    models::{
        ArticleResponse, ArticlesResponse, CreateArticleInput, ListArticlesQuery, UpdateArticleInput,
    },
    AppState,
};

pub async fn create_article(
    State(state): State<AppState>,
    AuthUser(user_id): AuthUser,
    Json(input): Json<CreateArticleInput>,
) -> AppResult<(StatusCode, Json<ArticleResponse>)> {
    let response = state.article_service.create(user_id, input).await?;

    Ok((StatusCode::CREATED, Json(response)))
}

pub async fn get_article(
    State(state): State<AppState>,
    OptionalAuthUser(user_id): OptionalAuthUser,
    Path(slug): Path<String>,
) -> AppResult<Json<ArticleResponse>> {
    let response = state.article_service.get(&slug, user_id).await?;

    Ok(Json(response))
}

pub async fn list_articles(
    State(state): State<AppState>,
    OptionalAuthUser(user_id): OptionalAuthUser,
    Query(query): Query<ListArticlesQuery>,
) -> AppResult<Json<ArticlesResponse>> {
    let response = state.article_service.list(query, user_id).await?;

    Ok(Json(response))
}

pub async fn update_article(
    State(state): State<AppState>,
    AuthUser(user_id): AuthUser,
    Path(slug): Path<String>,
    Json(input): Json<UpdateArticleInput>,
) -> AppResult<Json<ArticleResponse>> {
    let response = state.article_service.update(&slug, user_id, input).await?;

    Ok(Json(response))
}

pub async fn delete_article(
    State(state): State<AppState>,
    AuthUser(user_id): AuthUser,
    Path(slug): Path<String>,
) -> AppResult<StatusCode> {
    state.article_service.delete(&slug, user_id).await?;

    Ok(StatusCode::NO_CONTENT)
}

pub async fn favorite_article(
    State(state): State<AppState>,
    AuthUser(user_id): AuthUser,
    Path(slug): Path<String>,
) -> AppResult<Json<ArticleResponse>> {
    let response = state.article_service.favorite(&slug, user_id).await?;

    Ok(Json(response))
}

pub async fn unfavorite_article(
    State(state): State<AppState>,
    AuthUser(user_id): AuthUser,
    Path(slug): Path<String>,
) -> AppResult<Json<ArticleResponse>> {
    let response = state.article_service.unfavorite(&slug, user_id).await?;

    Ok(Json(response))
}
