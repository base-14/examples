using Api.Data;
using Api.Services;
using Microsoft.EntityFrameworkCore;
using OpenTelemetry.Logs;
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;
using Worker;

var builder = Host.CreateApplicationBuilder(args);

var serviceName = builder.Configuration["OTEL_SERVICE_NAME"] ?? "dotnet-sqlserver-worker";

builder.Services.AddDbContext<AppDbContext>(options =>
    options.UseSqlServer(builder.Configuration.GetConnectionString("DefaultConnection")));

builder.Services.AddScoped<JobQueue>();

builder.Services.AddOpenTelemetry()
    .ConfigureResource(resource => resource
        .AddService(serviceName)
        .AddAttributes([
            new KeyValuePair<string, object>("deployment.environment",
                builder.Environment.EnvironmentName.ToLowerInvariant())
        ]))
    .WithTracing(tracing => tracing
        .AddSqlClientInstrumentation(options =>
        {
            options.SetDbStatementForText = true;
            options.RecordException = true;
        })
        .AddSource("DotnetSqlServer.Worker")
        .AddSource("DotnetSqlServer.JobQueue")
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

builder.Services.AddHostedService<JobProcessor>();

var host = builder.Build();
host.Run();
