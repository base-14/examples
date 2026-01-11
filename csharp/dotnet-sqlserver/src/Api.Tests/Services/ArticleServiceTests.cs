using Api.Data.Entities;
using Api.Models;
using Api.Services;
using Microsoft.Extensions.Logging;
using Moq;

namespace Api.Tests.Services;

public class ArticleServiceTests : IDisposable
{
    private readonly Api.Data.AppDbContext _context;
    private readonly Mock<JobQueue> _mockJobQueue;
    private readonly ArticleService _articleService;
    private readonly User _testUser;

    public ArticleServiceTests()
    {
        _context = TestHelper.CreateInMemoryContext();
        _mockJobQueue = new Mock<JobQueue>(_context);
        var logger = new Mock<ILogger<ArticleService>>();
        _articleService = new ArticleService(_context, _mockJobQueue.Object, logger.Object);

        _testUser = new User
        {
            Email = "test@example.com",
            PasswordHash = "hash",
            Name = "Test User"
        };
        _context.Users.Add(_testUser);
        _context.SaveChanges();
    }

    public void Dispose()
    {
        _context.Dispose();
    }

    [Fact]
    public async Task CreateAsync_WithValidData_CreatesArticle()
    {
        var request = new CreateArticleRequest("Test Title", "Description", "Body content");

        var result = await _articleService.CreateAsync(_testUser.Id, request);

        Assert.NotNull(result);
        Assert.Equal("Test Title", result.Title);
        Assert.Equal("Description", result.Description);
        Assert.Equal("Body content", result.Body);
        Assert.Contains("test-title", result.Slug);
    }

    [Fact]
    public async Task GetArticlesAsync_ReturnsPaginatedResults()
    {
        for (int i = 0; i < 5; i++)
        {
            _context.Articles.Add(new Article
            {
                Slug = $"article-{i}",
                Title = $"Article {i}",
                Body = "Body",
                AuthorId = _testUser.Id
            });
        }
        await _context.SaveChangesAsync();

        var result = await _articleService.GetArticlesAsync(null, limit: 3, offset: 0);

        Assert.Equal(3, result.Articles.Count());
        Assert.Equal(5, result.ArticlesCount);
    }

    [Fact]
    public async Task GetBySlugAsync_WithExistingArticle_ReturnsArticle()
    {
        var article = new Article
        {
            Slug = "test-slug",
            Title = "Test Article",
            Body = "Body",
            AuthorId = _testUser.Id
        };
        _context.Articles.Add(article);
        await _context.SaveChangesAsync();

        var result = await _articleService.GetBySlugAsync("test-slug", null);

        Assert.NotNull(result);
        Assert.Equal("Test Article", result.Title);
    }

    [Fact]
    public async Task GetBySlugAsync_WithNonExistentSlug_ReturnsNull()
    {
        var result = await _articleService.GetBySlugAsync("non-existent-slug", null);

        Assert.Null(result);
    }

    [Fact]
    public async Task UpdateAsync_AsOwner_UpdatesArticle()
    {
        var article = new Article
        {
            Slug = "update-test",
            Title = "Original Title",
            Body = "Original Body",
            AuthorId = _testUser.Id
        };
        _context.Articles.Add(article);
        await _context.SaveChangesAsync();

        var request = new UpdateArticleRequest("Updated Title", null, "Updated Body");
        var result = await _articleService.UpdateAsync("update-test", _testUser.Id, request);

        Assert.NotNull(result);
        Assert.Equal("Updated Title", result.Title);
        Assert.Equal("Updated Body", result.Body);
    }

    [Fact]
    public async Task UpdateAsync_AsNonOwner_ThrowsUnauthorizedAccessException()
    {
        var otherUser = new User { Email = "other@example.com", PasswordHash = "hash", Name = "Other" };
        _context.Users.Add(otherUser);

        var article = new Article
        {
            Slug = "owner-test",
            Title = "Title",
            Body = "Body",
            AuthorId = _testUser.Id
        };
        _context.Articles.Add(article);
        await _context.SaveChangesAsync();

        var request = new UpdateArticleRequest("Hacked", null, null);

        await Assert.ThrowsAsync<UnauthorizedAccessException>(
            () => _articleService.UpdateAsync("owner-test", otherUser.Id, request));
    }

    [Fact]
    public async Task DeleteAsync_AsOwner_DeletesArticle()
    {
        var article = new Article
        {
            Slug = "delete-test",
            Title = "To Delete",
            Body = "Body",
            AuthorId = _testUser.Id
        };
        _context.Articles.Add(article);
        await _context.SaveChangesAsync();

        var result = await _articleService.DeleteAsync("delete-test", _testUser.Id);

        Assert.True(result);
        Assert.Null(await _context.Articles.FindAsync(article.Id));
    }

    [Fact]
    public async Task DeleteAsync_AsNonOwner_ThrowsUnauthorizedAccessException()
    {
        var otherUser = new User { Email = "other2@example.com", PasswordHash = "hash", Name = "Other" };
        _context.Users.Add(otherUser);

        var article = new Article
        {
            Slug = "delete-owner-test",
            Title = "Title",
            Body = "Body",
            AuthorId = _testUser.Id
        };
        _context.Articles.Add(article);
        await _context.SaveChangesAsync();

        await Assert.ThrowsAsync<UnauthorizedAccessException>(
            () => _articleService.DeleteAsync("delete-owner-test", otherUser.Id));
    }

    [Fact]
    public async Task DeleteAsync_WithNonExistentSlug_ReturnsFalse()
    {
        var result = await _articleService.DeleteAsync("non-existent", _testUser.Id);

        Assert.False(result);
    }
}
