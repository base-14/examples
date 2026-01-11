using Api.Data;

namespace Api.Endpoints;

public static class HealthEndpoints
{
    public static RouteGroupBuilder MapHealthEndpoints(this RouteGroupBuilder group)
    {
        group.MapGet("/health", async (AppDbContext db) =>
        {
            var dbHealthy = false;
            try
            {
                dbHealthy = await db.Database.CanConnectAsync();
            }
            catch
            {
                // Database connection failed
            }

            var health = new
            {
                status = dbHealthy ? "healthy" : "unhealthy",
                timestamp = DateTime.UtcNow,
                components = new
                {
                    database = dbHealthy ? "healthy" : "unhealthy"
                }
            };

            return dbHealthy
                ? Results.Ok(health)
                : Results.Json(health, statusCode: 503);
        })
        .WithName("HealthCheck")
        .WithOpenApi();

        return group;
    }
}
