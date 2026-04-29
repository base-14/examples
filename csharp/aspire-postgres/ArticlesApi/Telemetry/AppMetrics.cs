using System.Diagnostics;
using System.Diagnostics.Metrics;

namespace ArticlesApi.Telemetry;

// Names must match .AddSource() / .AddMeter() in ServiceDefaults
// or the SDK drops everything from here.
public static class AppMetrics
{
    public const string MeterName = "AspirePostgres.Articles";
    public const string ActivitySourceName = "AspirePostgres.Articles";

    public static readonly Meter Meter = new(MeterName);

    public static readonly Counter<long> ArticlesCreated =
        Meter.CreateCounter<long>("articles.created", description: "Total articles created");

    public static readonly ActivitySource ActivitySource = new(ActivitySourceName);
}
