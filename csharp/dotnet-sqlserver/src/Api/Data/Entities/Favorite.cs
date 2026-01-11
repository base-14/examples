namespace Api.Data.Entities;

public class Favorite
{
    public int Id { get; set; }
    public int UserId { get; set; }
    public User User { get; set; } = null!;
    public int ArticleId { get; set; }
    public Article Article { get; set; } = null!;
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
}
