using System.ComponentModel.DataAnnotations;

namespace Api.Models;

public record CreateArticleRequest(
    [Required, MaxLength(500)] string Title,
    [MaxLength(1000)] string? Description,
    [Required] string Body
);

public record UpdateArticleRequest(
    [MaxLength(500)] string? Title,
    [MaxLength(1000)] string? Description,
    string? Body
);

public record AuthorResponse(
    int Id,
    string? Name,
    string? Bio,
    string? Image
);

public record ArticleResponse(
    int Id,
    string Slug,
    string Title,
    string? Description,
    string Body,
    int FavoritesCount,
    bool Favorited,
    DateTime CreatedAt,
    DateTime UpdatedAt,
    AuthorResponse Author
);

public record ArticleListResponse(
    IEnumerable<ArticleResponse> Articles,
    int ArticlesCount
);
