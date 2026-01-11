using System.Security.Claims;
using Api.Filters;
using Api.Models;
using Api.Services;

namespace Api.Endpoints;

public static class AuthEndpoints
{
    public static RouteGroupBuilder MapAuthEndpoints(this RouteGroupBuilder group)
    {
        group.MapPost("/register", async (RegisterRequest request, AuthService authService) =>
        {
            try
            {
                var (user, token) = await authService.RegisterAsync(request);
                return Results.Created($"/api/user", new AuthResponse(user, token));
            }
            catch (InvalidOperationException ex)
            {
                return Results.Conflict(new { error = ex.Message });
            }
        })
        .AddEndpointFilter<ValidationFilter<RegisterRequest>>()
        .WithName("Register")
        .WithOpenApi();

        group.MapPost("/login", async (LoginRequest request, AuthService authService) =>
        {
            var result = await authService.LoginAsync(request.Email, request.Password);
            if (result is null)
                return Results.Json(new { error = "Invalid credentials" }, statusCode: 401);

            return Results.Ok(new AuthResponse(result.Value.User, result.Value.Token));
        })
        .AddEndpointFilter<ValidationFilter<LoginRequest>>()
        .WithName("Login")
        .WithOpenApi();

        group.MapGet("/user", async (ClaimsPrincipal principal, AuthService authService) =>
        {
            var userIdClaim = principal.FindFirst(ClaimTypes.NameIdentifier)?.Value;
            if (userIdClaim is null || !int.TryParse(userIdClaim, out var userId))
                return Results.Unauthorized();

            var user = await authService.GetByIdAsync(userId);
            return user is null ? Results.NotFound() : Results.Ok(user);
        })
        .RequireAuthorization()
        .WithName("GetCurrentUser")
        .WithOpenApi();

        group.MapPost("/logout", () => Results.Ok(new { message = "Logged out successfully" }))
        .RequireAuthorization()
        .WithName("Logout")
        .WithOpenApi();

        return group;
    }
}
