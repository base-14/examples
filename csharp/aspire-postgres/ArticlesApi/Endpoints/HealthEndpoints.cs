using ArticlesApi.Data;
using ArticlesApi.Models;
using Microsoft.EntityFrameworkCore;

namespace ArticlesApi.Endpoints;

public static class HealthEndpoints
{
    public static IEndpointRouteBuilder MapHealthEndpoints(this IEndpointRouteBuilder app)
    {
        app.MapGet("/api/health", async (
            AppDbContext db,
            ILogger<Program> logger,
            CancellationToken ct) =>
        {
            bool dbOk;
            try
            {
                dbOk = await db.Database.CanConnectAsync(ct);
            }
            catch (Exception ex)
            {
                logger.LogWarning(ex, "DB ping threw; reporting degraded");
                dbOk = false;
            }

            var payload = ApiResponseFactory.Ok(new
            {
                status = dbOk ? "healthy" : "degraded",
                db = dbOk ? "ok" : "down",
            });

            return dbOk
                ? Results.Ok(payload)
                : Results.Json(payload, statusCode: StatusCodes.Status503ServiceUnavailable);
        });

        return app;
    }
}
