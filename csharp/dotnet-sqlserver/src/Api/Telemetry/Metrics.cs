using System.Diagnostics.Metrics;

namespace Api.Telemetry;

public static class AppMetrics
{
    private static readonly Meter Meter = new("DotnetSqlServer.Metrics");

    public static readonly Counter<long> UsersRegistered =
        Meter.CreateCounter<long>("users.registered", description: "Total users registered");

    public static readonly Counter<long> LoginAttempts =
        Meter.CreateCounter<long>("auth.login.attempts", description: "Total login attempts");

    public static readonly Counter<long> LoginFailures =
        Meter.CreateCounter<long>("auth.login.failures", description: "Total failed login attempts");

    public static readonly Counter<long> ArticlesCreated =
        Meter.CreateCounter<long>("articles.created", description: "Total articles created");

    public static readonly Counter<long> ArticlesUpdated =
        Meter.CreateCounter<long>("articles.updated", description: "Total articles updated");

    public static readonly Counter<long> ArticlesDeleted =
        Meter.CreateCounter<long>("articles.deleted", description: "Total articles deleted");

    public static readonly Counter<long> FavoritesAdded =
        Meter.CreateCounter<long>("favorites.added", description: "Total favorites added");

    public static readonly Counter<long> FavoritesRemoved =
        Meter.CreateCounter<long>("favorites.removed", description: "Total favorites removed");

    public static readonly Counter<long> JobsEnqueued =
        Meter.CreateCounter<long>("jobs.enqueued", description: "Total jobs enqueued");

    public static readonly Counter<long> JobsCompleted =
        Meter.CreateCounter<long>("jobs.completed", description: "Total jobs completed");

    public static readonly Counter<long> JobsFailed =
        Meter.CreateCounter<long>("jobs.failed", description: "Total jobs failed");
}
