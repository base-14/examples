using System.Text.Json.Serialization;
using ServiceDefaults;

var builder = WebApplication.CreateBuilder(args);

builder.AddServiceDefaults();

var app = builder.Build();

app.MapDefaultEndpoints();

app.MapPost("/notify", (NotifyPayload payload, ILogger<Program> logger) =>
{
    logger.LogInformation(
        "Notification sent for article: id={ArticleId} title={Title}",
        payload.ArticleId, payload.Title);
    return Results.Ok(new { received = true });
});

app.Run();

public record NotifyPayload(
    [property: JsonPropertyName("article_id")] int ArticleId,
    [property: JsonPropertyName("title")] string Title);

public partial class Program { }
