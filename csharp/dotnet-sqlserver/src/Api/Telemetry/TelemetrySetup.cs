using OpenTelemetry.Exporter;
using OpenTelemetry.Logs;
using OpenTelemetry.Metrics;
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;

namespace Api.Telemetry;

public static class TelemetrySetup
{
    public static WebApplicationBuilder AddTelemetry(this WebApplicationBuilder builder)
    {
        var serviceName = builder.Configuration["OTEL_SERVICE_NAME"] ?? "dotnet-sqlserver";

        builder.Services.AddOpenTelemetry()
            .ConfigureResource(resource => resource
                .AddService(serviceName)
                .AddAttributes([
                    new KeyValuePair<string, object>("deployment.environment",
                        builder.Environment.EnvironmentName.ToLowerInvariant())
                ]))
            .WithTracing(tracing => tracing
                .AddAspNetCoreInstrumentation(options =>
                {
                    options.RecordException = true;
                })
                .AddHttpClientInstrumentation()
                .AddSqlClientInstrumentation(options =>
                {
                    options.SetDbStatementForText = true;
                    options.RecordException = true;
                })
                .AddSource("DotnetSqlServer.AuthService")
                .AddSource("DotnetSqlServer.ArticleService")
                .AddSource("DotnetSqlServer.JobQueue")
                .AddOtlpExporter())
            .WithMetrics(metrics => metrics
                .SetExemplarFilter(ExemplarFilterType.TraceBased)
                .AddAspNetCoreInstrumentation()
                .AddHttpClientInstrumentation()
                .AddRuntimeInstrumentation()
                .AddMeter("DotnetSqlServer.Metrics")
                .AddOtlpExporter());

        builder.Logging.AddOpenTelemetry(logging =>
        {
            logging.IncludeFormattedMessage = true;
            logging.IncludeScopes = true;
            logging.AddOtlpExporter();
        });

        builder.Logging.Configure(options =>
        {
            options.ActivityTrackingOptions =
                ActivityTrackingOptions.TraceId |
                ActivityTrackingOptions.SpanId |
                ActivityTrackingOptions.ParentId;
        });

        return builder;
    }
}
