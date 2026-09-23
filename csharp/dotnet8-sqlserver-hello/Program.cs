using HelloSqlServer;

var builder = WebApplication.CreateBuilder(args);

var connectionString = builder.Configuration.GetConnectionString("DefaultConnection")
    ?? throw new InvalidOperationException("ConnectionStrings__DefaultConnection is not set");

builder.Services.AddSingleton(new GreetingStore(connectionString));

var app = builder.Build();

await app.Services.GetRequiredService<GreetingStore>().EnsureSchemaAsync(app.Lifetime.ApplicationStopping);

app.MapGet("/api/health", async (GreetingStore store, CancellationToken ct) =>
{
    await store.PingAsync(ct);
    return Results.Ok(new { status = "healthy" });
});

app.MapGet("/api/hello/{name}", async (string name, GreetingStore store, ILogger<Program> logger, CancellationToken ct) =>
{
    var count = await store.RecordGreetingAsync(name, ct);
    logger.LogInformation("Greeted {Name}; {Count} greetings stored so far", name, count);
    return Results.Ok(new { message = $"Hello, {name}!", greetingCount = count });
});

app.Run();
