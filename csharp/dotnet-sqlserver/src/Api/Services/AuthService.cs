using System.Diagnostics;
using System.IdentityModel.Tokens.Jwt;
using System.Security.Claims;
using System.Text;
using Api.Data;
using Api.Data.Entities;
using Api.Models;
using Api.Telemetry;
using Microsoft.EntityFrameworkCore;
using Microsoft.IdentityModel.Tokens;
using OpenTelemetry.Trace;

namespace Api.Services;

public class AuthService(AppDbContext context, IConfiguration config, ILogger<AuthService> logger)
{
    private static readonly ActivitySource ActivitySource = new("DotnetSqlServer.AuthService");

    public async Task<(UserResponse User, string Token)> RegisterAsync(RegisterRequest request)
    {
        using var activity = ActivitySource.StartActivity("user.register");
        activity?.SetTag("user.email_domain", request.Email.Split('@')[1]);

        var existingUser = await context.Users
            .FirstOrDefaultAsync(u => u.Email == request.Email);

        if (existingUser is not null)
        {
            logger.LogWarning("Registration failed: email already registered {Email}", request.Email);
            var ex = new InvalidOperationException("Email already registered");
            activity?.SetStatus(ActivityStatusCode.Error, ex.Message);
            activity?.AddException(ex);
            throw ex;
        }

        var user = new User
        {
            Email = request.Email,
            PasswordHash = BCrypt.Net.BCrypt.HashPassword(request.Password),
            Name = request.Name
        };

        context.Users.Add(user);
        await context.SaveChangesAsync();

        activity?.SetTag("user.id", user.Id);
        AppMetrics.UsersRegistered.Add(1);

        logger.LogInformation("User registered: {UserId}", user.Id);

        var token = GenerateToken(user);
        return (ToUserResponse(user), token);
    }

    public async Task<(UserResponse User, string Token)?> LoginAsync(string email, string password)
    {
        using var activity = ActivitySource.StartActivity("user.login");
        AppMetrics.LoginAttempts.Add(1);

        var user = await context.Users
            .FirstOrDefaultAsync(u => u.Email == email);

        if (user is null || !BCrypt.Net.BCrypt.Verify(password, user.PasswordHash))
        {
            logger.LogWarning("Login failed for {Email}", email);
            activity?.SetTag("auth.success", false);
            AppMetrics.LoginFailures.Add(1);
            return null;
        }

        activity?.SetTag("auth.success", true);
        activity?.SetTag("user.id", user.Id);

        logger.LogInformation("User logged in: {UserId}", user.Id);

        var token = GenerateToken(user);
        return (ToUserResponse(user), token);
    }

    public async Task<UserResponse?> GetByIdAsync(int userId)
    {
        using var activity = ActivitySource.StartActivity("user.get_by_id");
        activity?.SetTag("user.id", userId);

        var user = await context.Users.FindAsync(userId);
        return user is null ? null : ToUserResponse(user);
    }

    private string GenerateToken(User user)
    {
        var claims = new[]
        {
            new Claim(ClaimTypes.NameIdentifier, user.Id.ToString()),
            new Claim(ClaimTypes.Email, user.Email),
            new Claim(JwtRegisteredClaimNames.Jti, Guid.NewGuid().ToString())
        };

        var key = new SymmetricSecurityKey(
            Encoding.UTF8.GetBytes(config["Jwt:Secret"]!));
        var creds = new SigningCredentials(key, SecurityAlgorithms.HmacSha256);

        var expirationHours = int.Parse(config["Jwt:ExpirationHours"] ?? "168");
        var token = new JwtSecurityToken(
            issuer: config["Jwt:Issuer"],
            audience: config["Jwt:Audience"],
            claims: claims,
            expires: DateTime.UtcNow.AddHours(expirationHours),
            signingCredentials: creds
        );

        return new JwtSecurityTokenHandler().WriteToken(token);
    }

    private static UserResponse ToUserResponse(User user) =>
        new(user.Id, user.Email, user.Name, user.Bio, user.Image);
}
