using System.Net.Http.Json;

namespace ArticlesApi.Services;

public class NotifyService(HttpClient client, ILogger<NotifyService> logger)
{
    public async Task NotifyArticleCreatedAsync(int articleId, string title, CancellationToken cancellationToken)
    {
        try
        {
            var response = await client.PostAsJsonAsync(
                "/notify",
                new { article_id = articleId, title },
                cancellationToken);
            response.EnsureSuccessStatusCode();
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex,
                "Notify call failed for article {ArticleId}; downstream notify-svc unreachable",
                articleId);
        }
    }
}
