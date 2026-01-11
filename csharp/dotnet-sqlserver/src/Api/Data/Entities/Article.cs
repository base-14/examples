using System.ComponentModel.DataAnnotations;

namespace Api.Data.Entities;

public class Article
{
    public int Id { get; set; }

    [Required, MaxLength(255)]
    public string Slug { get; set; } = null!;

    [Required, MaxLength(500)]
    public string Title { get; set; } = null!;

    [MaxLength(1000)]
    public string? Description { get; set; }

    [Required]
    public string Body { get; set; } = null!;

    public int AuthorId { get; set; }
    public User Author { get; set; } = null!;

    public int FavoritesCount { get; set; }

    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
    public DateTime UpdatedAt { get; set; } = DateTime.UtcNow;

    public ICollection<Favorite> Favorites { get; set; } = [];
}
