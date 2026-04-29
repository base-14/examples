using ArticlesApi.Data;
using ArticlesApi.Endpoints;
using ArticlesApi.Services;
using Microsoft.EntityFrameworkCore;
using ServiceDefaults;

var builder = WebApplication.CreateBuilder(args);

builder.AddServiceDefaults();

var connectionString = builder.Configuration.GetConnectionString("articles")
    ?? builder.Configuration["ConnectionStrings:articles"]
    ?? throw new InvalidOperationException(
        "ConnectionStrings:articles is required (Aspire injects from postgres resource; Compose mode sets it explicitly).");

builder.Services.AddDbContext<AppDbContext>(options =>
    options.UseNpgsql(connectionString));

var notifyBaseUrl = builder.Configuration["Notify:BaseUrl"]
    ?? throw new InvalidOperationException(
        "Notify:BaseUrl is required (set via Aspire WithEnvironment or Compose).");

builder.Services.AddHttpClient<NotifyService>(client =>
{
    client.BaseAddress = new Uri(notifyBaseUrl);
    client.Timeout = TimeSpan.FromSeconds(5);
});

var app = builder.Build();

app.MapDefaultEndpoints();
app.MapHealthEndpoints();
app.MapArticleEndpoints();

using (var scope = app.Services.CreateScope())
{
    var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
    db.Database.EnsureCreated();
}

app.Run();

public partial class Program { }
