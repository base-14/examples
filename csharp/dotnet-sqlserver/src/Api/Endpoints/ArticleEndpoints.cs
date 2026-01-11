using System.Security.Claims;
using Api.Filters;
using Api.Models;
using Api.Services;

namespace Api.Endpoints;

public static class ArticleEndpoints
{
    public static RouteGroupBuilder MapArticleEndpoints(this RouteGroupBuilder group)
    {
        var articles = group.MapGroup("/articles");

        articles.MapGet("/", async (
            int? limit,
            int? offset,
            ClaimsPrincipal principal,
            ArticleService articleService) =>
        {
            var userId = GetUserId(principal);
            var result = await articleService.GetArticlesAsync(userId, limit ?? 20, offset ?? 0);
            return Results.Ok(result);
        })
        .WithName("GetArticles")
        .WithOpenApi();

        articles.MapPost("/", async (
            CreateArticleRequest request,
            ClaimsPrincipal principal,
            ArticleService articleService) =>
        {
            var userId = GetUserId(principal);
            if (userId is null)
                return Results.Unauthorized();

            var article = await articleService.CreateAsync(userId.Value, request);
            return Results.Created($"/api/articles/{article.Slug}", article);
        })
        .AddEndpointFilter<ValidationFilter<CreateArticleRequest>>()
        .RequireAuthorization()
        .WithName("CreateArticle")
        .WithOpenApi();

        articles.MapGet("/{slug}", async (
            string slug,
            ClaimsPrincipal principal,
            ArticleService articleService) =>
        {
            var userId = GetUserId(principal);
            var article = await articleService.GetBySlugAsync(slug, userId);
            return article is null
                ? Results.NotFound(new { error = "Article not found" })
                : Results.Ok(article);
        })
        .WithName("GetArticle")
        .WithOpenApi();

        articles.MapPut("/{slug}", async (
            string slug,
            UpdateArticleRequest request,
            ClaimsPrincipal principal,
            ArticleService articleService) =>
        {
            var userId = GetUserId(principal);
            if (userId is null)
                return Results.Unauthorized();

            try
            {
                var article = await articleService.UpdateAsync(slug, userId.Value, request);
                return article is null
                    ? Results.NotFound(new { error = "Article not found" })
                    : Results.Ok(article);
            }
            catch (UnauthorizedAccessException)
            {
                return Results.Forbid();
            }
        })
        .AddEndpointFilter<ValidationFilter<UpdateArticleRequest>>()
        .RequireAuthorization()
        .WithName("UpdateArticle")
        .WithOpenApi();

        articles.MapDelete("/{slug}", async (
            string slug,
            ClaimsPrincipal principal,
            ArticleService articleService) =>
        {
            var userId = GetUserId(principal);
            if (userId is null)
                return Results.Unauthorized();

            try
            {
                var deleted = await articleService.DeleteAsync(slug, userId.Value);
                return deleted
                    ? Results.NoContent()
                    : Results.NotFound(new { error = "Article not found" });
            }
            catch (UnauthorizedAccessException)
            {
                return Results.Forbid();
            }
        })
        .RequireAuthorization()
        .WithName("DeleteArticle")
        .WithOpenApi();

        articles.MapPost("/{slug}/favorite", async (
            string slug,
            ClaimsPrincipal principal,
            ArticleService articleService) =>
        {
            var userId = GetUserId(principal);
            if (userId is null)
                return Results.Unauthorized();

            var article = await articleService.FavoriteAsync(slug, userId.Value);
            return article is null
                ? Results.NotFound(new { error = "Article not found" })
                : Results.Ok(article);
        })
        .RequireAuthorization()
        .WithName("FavoriteArticle")
        .WithOpenApi();

        articles.MapDelete("/{slug}/favorite", async (
            string slug,
            ClaimsPrincipal principal,
            ArticleService articleService) =>
        {
            var userId = GetUserId(principal);
            if (userId is null)
                return Results.Unauthorized();

            var article = await articleService.UnfavoriteAsync(slug, userId.Value);
            return article is null
                ? Results.NotFound(new { error = "Article not found" })
                : Results.Ok(article);
        })
        .RequireAuthorization()
        .WithName("UnfavoriteArticle")
        .WithOpenApi();

        return group;
    }

    private static int? GetUserId(ClaimsPrincipal principal)
    {
        var userIdClaim = principal.FindFirst(ClaimTypes.NameIdentifier)?.Value;
        return int.TryParse(userIdClaim, out var userId) ? userId : null;
    }
}
