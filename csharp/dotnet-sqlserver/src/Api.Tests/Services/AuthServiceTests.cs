using Api.Models;
using Api.Services;
using Microsoft.Extensions.Logging;
using Moq;

namespace Api.Tests.Services;

public class AuthServiceTests : IDisposable
{
    private readonly Api.Data.AppDbContext _context;
    private readonly AuthService _authService;

    public AuthServiceTests()
    {
        _context = TestHelper.CreateInMemoryContext();
        var config = TestHelper.CreateTestConfiguration();
        var logger = new Mock<ILogger<AuthService>>();
        _authService = new AuthService(_context, config, logger.Object);
    }

    public void Dispose()
    {
        _context.Dispose();
    }

    [Fact]
    public async Task RegisterAsync_WithValidData_CreatesUser()
    {
        var request = new RegisterRequest("test@example.com", "password123", "Test User");

        var (user, token) = await _authService.RegisterAsync(request);

        Assert.NotNull(user);
        Assert.Equal("test@example.com", user.Email);
        Assert.Equal("Test User", user.Name);
        Assert.NotEmpty(token);
    }

    [Fact]
    public async Task RegisterAsync_WithDuplicateEmail_ThrowsException()
    {
        var request = new RegisterRequest("duplicate@example.com", "password123", "User 1");
        await _authService.RegisterAsync(request);

        var duplicateRequest = new RegisterRequest("duplicate@example.com", "password456", "User 2");

        await Assert.ThrowsAsync<InvalidOperationException>(
            () => _authService.RegisterAsync(duplicateRequest));
    }

    [Fact]
    public async Task LoginAsync_WithValidCredentials_ReturnsUserAndToken()
    {
        var request = new RegisterRequest("login@example.com", "password123", "Test User");
        await _authService.RegisterAsync(request);

        var result = await _authService.LoginAsync("login@example.com", "password123");

        Assert.NotNull(result);
        Assert.Equal("login@example.com", result.Value.User.Email);
        Assert.NotEmpty(result.Value.Token);
    }

    [Fact]
    public async Task LoginAsync_WithInvalidPassword_ReturnsNull()
    {
        var request = new RegisterRequest("user@example.com", "password123", "Test User");
        await _authService.RegisterAsync(request);

        var result = await _authService.LoginAsync("user@example.com", "wrongpassword");

        Assert.Null(result);
    }

    [Fact]
    public async Task LoginAsync_WithNonExistentEmail_ReturnsNull()
    {
        var result = await _authService.LoginAsync("nonexistent@example.com", "password123");

        Assert.Null(result);
    }

    [Fact]
    public async Task GetByIdAsync_WithExistingUser_ReturnsUser()
    {
        var request = new RegisterRequest("getbyid@example.com", "password123", "Test User");
        var (user, _) = await _authService.RegisterAsync(request);

        var result = await _authService.GetByIdAsync(user.Id);

        Assert.NotNull(result);
        Assert.Equal(user.Id, result.Id);
        Assert.Equal("getbyid@example.com", result.Email);
    }

    [Fact]
    public async Task GetByIdAsync_WithNonExistentId_ReturnsNull()
    {
        var result = await _authService.GetByIdAsync(99999);

        Assert.Null(result);
    }
}
