using System.ComponentModel.DataAnnotations;

namespace Api.Data.Entities;

public class User
{
    public int Id { get; set; }

    [Required, EmailAddress, MaxLength(255)]
    public string Email { get; set; } = null!;

    [Required, MaxLength(255)]
    public string PasswordHash { get; set; } = null!;

    [MaxLength(255)]
    public string? Name { get; set; }

    [MaxLength(1000)]
    public string? Bio { get; set; }

    [MaxLength(500)]
    public string? Image { get; set; }

    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
    public DateTime UpdatedAt { get; set; } = DateTime.UtcNow;

    public ICollection<Article> Articles { get; set; } = [];
    public ICollection<Favorite> Favorites { get; set; } = [];
}
