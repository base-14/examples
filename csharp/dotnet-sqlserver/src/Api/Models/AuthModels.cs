using System.ComponentModel.DataAnnotations;

namespace Api.Models;

public record RegisterRequest(
    [Required, EmailAddress] string Email,
    [Required, MinLength(8)] string Password,
    string? Name
);

public record LoginRequest(
    [Required, EmailAddress] string Email,
    [Required] string Password
);

public record UserResponse(
    int Id,
    string Email,
    string? Name,
    string? Bio,
    string? Image
);

public record AuthResponse(
    UserResponse User,
    string Token
);
