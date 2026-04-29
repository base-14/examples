using ArticlesApi.Data;
using ArticlesApi.Models;
using ArticlesApi.Services;
using ArticlesApi.Telemetry;
using Microsoft.EntityFrameworkCore;

namespace ArticlesApi.Endpoints;

public static class ArticleEndpoints
{
    public static IEndpointRouteBuilder MapArticleEndpoints(this IEndpointRouteBuilder app)
    {
        var group = app.MapGroup("/api/articles");

        group.MapGet("/", ListAsync);
        group.MapGet("/{id:int}", GetByIdAsync);
        group.MapPost("/", CreateAsync);
        group.MapPut("/{id:int}", UpdateAsync);
        group.MapDelete("/{id:int}", DeleteAsync);

        return app;
    }

    private static async Task<IResult> ListAsync(
        AppDbContext db,
        CancellationToken ct,
        int page = 1,
        int per_page = 20)
    {
        page = Math.Max(1, page);
        per_page = Math.Clamp(per_page, 1, 100);

        var total = await db.Articles.LongCountAsync(ct);
        var items = await db.Articles
            .AsNoTracking()
            .OrderByDescending(a => a.Id)
            .Skip((page - 1) * per_page)
            .Take(per_page)
            .Select(a => new ArticleResponse(a.Id, a.Title, a.Body, a.CreatedAt, a.UpdatedAt))
            .ToListAsync(ct);

        return Results.Ok(ApiResponseFactory.Ok(items, page, per_page, total));
    }

    private static async Task<IResult> GetByIdAsync(
        int id,
        AppDbContext db,
        ILogger<Program> logger,
        CancellationToken ct)
    {
        var article = await db.Articles.AsNoTracking().FirstOrDefaultAsync(a => a.Id == id, ct);
        if (article is null)
        {
            logger.LogWarning("Article not found: id={ArticleId}", id);
            return Results.NotFound(ApiResponseFactory.Error(
                "ARTICLE_NOT_FOUND",
                $"Article with id={id} not found"));
        }

        return Results.Ok(ApiResponseFactory.Ok(
            new ArticleResponse(article.Id, article.Title, article.Body, article.CreatedAt, article.UpdatedAt)));
    }

    private static async Task<IResult> CreateAsync(
        CreateArticleRequest request,
        AppDbContext db,
        NotifyService notify,
        ILogger<Program> logger,
        CancellationToken ct)
    {
        if (string.IsNullOrWhiteSpace(request.Title) || string.IsNullOrWhiteSpace(request.Body))
        {
            logger.LogWarning("Validation failed on create: title or body missing");
            return Results.UnprocessableEntity(ApiResponseFactory.Error(
                "VALIDATION_FAILED",
                "title and body are required"));
        }

        if (request.Title.Length > 255)
        {
            logger.LogWarning("Validation failed on create: title exceeds 255 chars");
            return Results.UnprocessableEntity(ApiResponseFactory.Error(
                "VALIDATION_FAILED",
                "title must be 255 characters or fewer"));
        }

        // Custom span under the ASP.NET Core HTTP server span.
        // `?.` is null-safe when the source is unregistered or sampled out.
        using var activity = AppMetrics.ActivitySource.StartActivity("article.create");

        var article = new Article { Title = request.Title.Trim(), Body = request.Body };
        db.Articles.Add(article);
        await db.SaveChangesAsync(ct);

        AppMetrics.ArticlesCreated.Add(1);
        activity?.SetTag("article.id", article.Id);

        logger.LogInformation("Article created: id={ArticleId} title={ArticleTitle}",
            article.Id, article.Title);

        await notify.NotifyArticleCreatedAsync(article.Id, article.Title, ct);

        return Results.Created(
            $"/api/articles/{article.Id}",
            ApiResponseFactory.Ok(
                new ArticleResponse(article.Id, article.Title, article.Body, article.CreatedAt, article.UpdatedAt)));
    }

    private static async Task<IResult> UpdateAsync(
        int id,
        UpdateArticleRequest request,
        AppDbContext db,
        ILogger<Program> logger,
        CancellationToken ct)
    {
        var article = await db.Articles.FirstOrDefaultAsync(a => a.Id == id, ct);
        if (article is null)
        {
            logger.LogWarning("Article not found on update: id={ArticleId}", id);
            return Results.NotFound(ApiResponseFactory.Error(
                "ARTICLE_NOT_FOUND",
                $"Article with id={id} not found"));
        }

        if (request.Title is { } title)
        {
            if (string.IsNullOrWhiteSpace(title) || title.Length > 255)
            {
                logger.LogWarning("Validation failed on update: invalid title length");
                return Results.UnprocessableEntity(ApiResponseFactory.Error(
                    "VALIDATION_FAILED",
                    "title must be non-empty and 255 characters or fewer"));
            }
            article.Title = title.Trim();
        }
        if (request.Body is { } body)
        {
            article.Body = body;
        }

        await db.SaveChangesAsync(ct);

        return Results.Ok(ApiResponseFactory.Ok(
            new ArticleResponse(article.Id, article.Title, article.Body, article.CreatedAt, article.UpdatedAt)));
    }

    private static async Task<IResult> DeleteAsync(
        int id,
        AppDbContext db,
        ILogger<Program> logger,
        CancellationToken ct)
    {
        var article = await db.Articles.FirstOrDefaultAsync(a => a.Id == id, ct);
        if (article is null)
        {
            logger.LogWarning("Article not found on delete: id={ArticleId}", id);
            return Results.NotFound(ApiResponseFactory.Error(
                "ARTICLE_NOT_FOUND",
                $"Article with id={id} not found"));
        }

        db.Articles.Remove(article);
        await db.SaveChangesAsync(ct);

        return Results.NoContent();
    }
}
