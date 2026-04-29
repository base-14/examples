using System.ComponentModel.DataAnnotations;

namespace ArticlesApi.Models;

public record ArticleResponse(
    int Id,
    string Title,
    string Body,
    DateTime CreatedAt,
    DateTime UpdatedAt);

public record CreateArticleRequest(
    [Required, MaxLength(255)] string Title,
    [Required] string Body);

public record UpdateArticleRequest(
    [MaxLength(255)] string? Title,
    string? Body);
