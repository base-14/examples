using System.Diagnostics;
using System.Text.RegularExpressions;
using Api.Data;
using Api.Data.Entities;
using Api.Models;
using Api.Telemetry;
using Microsoft.EntityFrameworkCore;
using OpenTelemetry;
using OpenTelemetry.Trace;

namespace Api.Services;

public partial class ArticleService(AppDbContext context, JobQueue jobQueue, ILogger<ArticleService> logger)
{
    private static readonly ActivitySource ActivitySource = new("DotnetSqlServer.ArticleService");

    public async Task<ArticleResponse> CreateAsync(int userId, CreateArticleRequest request)
    {
        using var activity = ActivitySource.StartActivity("article.create");
        activity?.SetTag("user.id", userId);

        var slug = GenerateSlug(request.Title);

        var article = new Article
        {
            Slug = slug,
            Title = request.Title,
            Description = request.Description,
            Body = request.Body,
            AuthorId = userId
        };

        context.Articles.Add(article);
        await context.SaveChangesAsync();

        activity?.SetTag("article.id", article.Id);
        activity?.SetTag("article.slug", slug);
        AppMetrics.ArticlesCreated.Add(1);

        logger.LogInformation("Article created: {ArticleId} by user {UserId}", article.Id, userId);

        Baggage.SetBaggage("user.id", userId.ToString());
        Baggage.SetBaggage("article.id", article.Id.ToString());
        await jobQueue.EnqueueAsync("notification", new { ArticleId = article.Id, Type = "article_created" });

        var author = await context.Users.FindAsync(userId);
        return ToArticleResponse(article, author!, false);
    }

    public async Task<ArticleListResponse> GetArticlesAsync(int? userId, int limit = 20, int offset = 0)
    {
        using var activity = ActivitySource.StartActivity("article.list");

        var query = context.Articles
            .Include(a => a.Author)
            .OrderByDescending(a => a.CreatedAt)
            .Skip(offset)
            .Take(limit);

        var articles = await query.ToListAsync();
        var totalCount = await context.Articles.CountAsync();

        var userFavorites = userId.HasValue
            ? await context.Favorites
                .Where(f => f.UserId == userId.Value)
                .Select(f => f.ArticleId)
                .ToHashSetAsync()
            : [];

        var responses = articles.Select(a =>
            ToArticleResponse(a, a.Author, userFavorites.Contains(a.Id)));

        return new ArticleListResponse(responses, totalCount);
    }

    public async Task<ArticleResponse?> GetBySlugAsync(string slug, int? userId)
    {
        using var activity = ActivitySource.StartActivity("article.get");
        activity?.SetTag("article.slug", slug);

        var article = await context.Articles
            .Include(a => a.Author)
            .FirstOrDefaultAsync(a => a.Slug == slug);

        if (article is null) return null;

        var favorited = userId.HasValue &&
            await context.Favorites.AnyAsync(f => f.UserId == userId.Value && f.ArticleId == article.Id);

        return ToArticleResponse(article, article.Author, favorited);
    }

    public async Task<ArticleResponse?> UpdateAsync(string slug, int userId, UpdateArticleRequest request)
    {
        using var activity = ActivitySource.StartActivity("article.update");
        activity?.SetTag("article.slug", slug);
        activity?.SetTag("user.id", userId);

        var article = await context.Articles
            .Include(a => a.Author)
            .FirstOrDefaultAsync(a => a.Slug == slug);

        if (article is null) return null;

        if (article.AuthorId != userId)
        {
            logger.LogWarning("Unauthorized update attempt on article {ArticleId} by user {UserId}", article.Id, userId);
            var ex = new UnauthorizedAccessException("Not authorized to update this article");
            activity?.SetStatus(ActivityStatusCode.Error, ex.Message);
            activity?.AddException(ex);
            throw ex;
        }

        if (request.Title is not null)
        {
            article.Title = request.Title;
            article.Slug = GenerateSlug(request.Title);
        }
        if (request.Description is not null) article.Description = request.Description;
        if (request.Body is not null) article.Body = request.Body;
        article.UpdatedAt = DateTime.UtcNow;

        await context.SaveChangesAsync();

        activity?.SetTag("article.id", article.Id);
        AppMetrics.ArticlesUpdated.Add(1);

        logger.LogInformation("Article updated: {ArticleId} by user {UserId}", article.Id, userId);

        var favorited = await context.Favorites.AnyAsync(f => f.UserId == userId && f.ArticleId == article.Id);
        return ToArticleResponse(article, article.Author, favorited);
    }

    public async Task<bool> DeleteAsync(string slug, int userId)
    {
        using var activity = ActivitySource.StartActivity("article.delete");
        activity?.SetTag("article.slug", slug);
        activity?.SetTag("user.id", userId);

        var article = await context.Articles.FirstOrDefaultAsync(a => a.Slug == slug);

        if (article is null) return false;

        if (article.AuthorId != userId)
        {
            logger.LogWarning("Unauthorized delete attempt on article {ArticleId} by user {UserId}", article.Id, userId);
            var ex = new UnauthorizedAccessException("Not authorized to delete this article");
            activity?.SetStatus(ActivityStatusCode.Error, ex.Message);
            activity?.AddException(ex);
            throw ex;
        }

        var articleId = article.Id;
        context.Articles.Remove(article);
        await context.SaveChangesAsync();

        activity?.SetTag("article.id", articleId);
        AppMetrics.ArticlesDeleted.Add(1);

        logger.LogInformation("Article deleted: {ArticleId} by user {UserId}", articleId, userId);

        return true;
    }

    public async Task<ArticleResponse?> FavoriteAsync(string slug, int userId)
    {
        using var activity = ActivitySource.StartActivity("article.favorite");
        activity?.SetTag("article.slug", slug);
        activity?.SetTag("user.id", userId);

        await using var transaction = await context.Database.BeginTransactionAsync();

        try
        {
            var article = await context.Articles
                .Include(a => a.Author)
                .FirstOrDefaultAsync(a => a.Slug == slug);

            if (article is null) return null;

            var existing = await context.Favorites
                .FirstOrDefaultAsync(f => f.UserId == userId && f.ArticleId == article.Id);

            if (existing is null)
            {
                context.Favorites.Add(new Favorite
                {
                    UserId = userId,
                    ArticleId = article.Id
                });
                await context.SaveChangesAsync();

                await context.Articles
                    .Where(a => a.Id == article.Id)
                    .ExecuteUpdateAsync(s => s.SetProperty(a => a.FavoritesCount, a => a.FavoritesCount + 1));

                article.FavoritesCount++;
                AppMetrics.FavoritesAdded.Add(1);

                logger.LogInformation("Article favorited: {ArticleId} by user {UserId}", article.Id, userId);
            }

            await transaction.CommitAsync();

            activity?.SetTag("article.id", article.Id);
            return ToArticleResponse(article, article.Author, true);
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "Failed to favorite article {Slug} by user {UserId}", slug, userId);
            activity?.SetStatus(ActivityStatusCode.Error, ex.Message);
            activity?.AddException(ex);
            await transaction.RollbackAsync();
            throw;
        }
    }

    public async Task<ArticleResponse?> UnfavoriteAsync(string slug, int userId)
    {
        using var activity = ActivitySource.StartActivity("article.unfavorite");
        activity?.SetTag("article.slug", slug);
        activity?.SetTag("user.id", userId);

        await using var transaction = await context.Database.BeginTransactionAsync();

        try
        {
            var article = await context.Articles
                .Include(a => a.Author)
                .FirstOrDefaultAsync(a => a.Slug == slug);

            if (article is null) return null;

            var favorite = await context.Favorites
                .FirstOrDefaultAsync(f => f.UserId == userId && f.ArticleId == article.Id);

            if (favorite is not null)
            {
                context.Favorites.Remove(favorite);
                await context.SaveChangesAsync();

                await context.Articles
                    .Where(a => a.Id == article.Id && a.FavoritesCount > 0)
                    .ExecuteUpdateAsync(s => s.SetProperty(a => a.FavoritesCount, a => a.FavoritesCount - 1));

                article.FavoritesCount = Math.Max(0, article.FavoritesCount - 1);
                AppMetrics.FavoritesRemoved.Add(1);

                logger.LogInformation("Article unfavorited: {ArticleId} by user {UserId}", article.Id, userId);
            }

            await transaction.CommitAsync();

            activity?.SetTag("article.id", article.Id);
            return ToArticleResponse(article, article.Author, false);
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "Failed to unfavorite article {Slug} by user {UserId}", slug, userId);
            activity?.SetStatus(ActivityStatusCode.Error, ex.Message);
            activity?.AddException(ex);
            await transaction.RollbackAsync();
            throw;
        }
    }

    private static string GenerateSlug(string title)
    {
        var slug = SlugRegex().Replace(title.ToLowerInvariant(), "");
        slug = WhitespaceRegex().Replace(slug, "-");
        return $"{slug}-{Guid.NewGuid().ToString()[..8]}";
    }

    private static ArticleResponse ToArticleResponse(Article article, User author, bool favorited) =>
        new(
            article.Id,
            article.Slug,
            article.Title,
            article.Description,
            article.Body,
            article.FavoritesCount,
            favorited,
            article.CreatedAt,
            article.UpdatedAt,
            new AuthorResponse(author.Id, author.Name, author.Bio, author.Image)
        );

    [GeneratedRegex("[^a-z0-9\\s-]")]
    private static partial Regex SlugRegex();

    [GeneratedRegex("\\s+")]
    private static partial Regex WhitespaceRegex();
}
