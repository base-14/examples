use actix_web::{HttpResponse, web};

use crate::{
    error::AppResult,
    middleware::{AuthUser, OptionalAuthUser},
    models::{CreateArticleInput, ListArticlesQuery, UpdateArticleInput},
    services::ArticleService,
};

pub async fn create_article(
    article_service: web::Data<ArticleService>,
    auth: AuthUser,
    input: web::Json<CreateArticleInput>,
) -> AppResult<HttpResponse> {
    let response = article_service.create(auth.0, input.into_inner()).await?;

    Ok(HttpResponse::Created().json(response))
}

pub async fn get_article(
    article_service: web::Data<ArticleService>,
    auth: OptionalAuthUser,
    slug: web::Path<String>,
) -> AppResult<HttpResponse> {
    let response = article_service.get(&slug, auth.0).await?;

    Ok(HttpResponse::Ok().json(response))
}

pub async fn list_articles(
    article_service: web::Data<ArticleService>,
    auth: OptionalAuthUser,
    query: web::Query<ListArticlesQuery>,
) -> AppResult<HttpResponse> {
    let response = article_service.list(query.into_inner(), auth.0).await?;

    Ok(HttpResponse::Ok().json(response))
}

pub async fn update_article(
    article_service: web::Data<ArticleService>,
    auth: AuthUser,
    slug: web::Path<String>,
    input: web::Json<UpdateArticleInput>,
) -> AppResult<HttpResponse> {
    let response = article_service
        .update(&slug, auth.0, input.into_inner())
        .await?;

    Ok(HttpResponse::Ok().json(response))
}

pub async fn delete_article(
    article_service: web::Data<ArticleService>,
    auth: AuthUser,
    slug: web::Path<String>,
) -> AppResult<HttpResponse> {
    article_service.delete(&slug, auth.0).await?;

    Ok(HttpResponse::NoContent().finish())
}

pub async fn favorite_article(
    article_service: web::Data<ArticleService>,
    auth: AuthUser,
    slug: web::Path<String>,
) -> AppResult<HttpResponse> {
    let response = article_service.favorite(&slug, auth.0).await?;

    Ok(HttpResponse::Ok().json(response))
}

pub async fn unfavorite_article(
    article_service: web::Data<ArticleService>,
    auth: AuthUser,
    slug: web::Path<String>,
) -> AppResult<HttpResponse> {
    let response = article_service.unfavorite(&slug, auth.0).await?;

    Ok(HttpResponse::Ok().json(response))
}
