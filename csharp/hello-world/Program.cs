// C# Hello World — OpenTelemetry

using System.Diagnostics;
using System.Diagnostics.Metrics;
using System.Runtime.InteropServices;
using Microsoft.Extensions.Logging;
using OpenTelemetry;
using OpenTelemetry.Exporter;
using OpenTelemetry.Logs;
using OpenTelemetry.Metrics;
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;

// -- Configuration ----------------------------------------------------------
// The collector endpoint. Set this to where your OTel collector accepts
// OTLP/HTTP traffic (default port 4318).
var endpoint = Environment.GetEnvironmentVariable("OTEL_EXPORTER_OTLP_ENDPOINT");
if (string.IsNullOrEmpty(endpoint))
{
    Console.Error.WriteLine("Set OTEL_EXPORTER_OTLP_ENDPOINT (e.g. http://localhost:4318)");
    Environment.Exit(1);
}

// A Resource identifies your application in the telemetry backend.
// Every span, log, and metric carries this identity.
var resource = ResourceBuilder.CreateDefault()
    .AddService("hello-world-csharp")
    .AddAttributes(new Dictionary<string, object>
    {
        ["process.runtime.name"] = ".NET",
        ["process.runtime.version"] = Environment.Version.ToString(),
        ["process.pid"] = Environment.ProcessId,
        ["os.type"] = Environment.OSVersion.Platform.ToString(),
        ["os.version"] = Environment.OSVersion.Version.ToString(),
        ["host.arch"] = RuntimeInformation.ProcessArchitecture.ToString(),
    });

// -- Traces -----------------------------------------------------------------
// A TracerProvider manages the lifecycle of traces. It batches spans and
// sends them to the collector via the OTLP/HTTP exporter.
// .NET uses System.Diagnostics.ActivitySource as its tracing API.
var activitySource = new ActivitySource("hello-world-csharp");
var tracerProvider = Sdk.CreateTracerProviderBuilder()
    .SetResourceBuilder(resource)
    .AddSource("hello-world-csharp")
    .AddOtlpExporter(o =>
    {
        o.Endpoint = new Uri($"{endpoint}/v1/traces");
        o.Protocol = OtlpExportProtocol.HttpProtobuf;
    })
    .Build()!;

// -- Logs -------------------------------------------------------------------
// .NET's OTel SDK routes logging through ILogger — the direct OTel Logs API
// is internal. Logs emitted inside an Activity (span) automatically carry
// the trace ID and span ID — this is called log-trace correlation.
// .NET severity names differ from other languages: Information (not INFO),
// Warning (not WARN), Error (not ERROR). The OTel severity numbers are the
// same across all languages (9, 13, 17).
var loggerFactory = LoggerFactory.Create(builder =>
{
    builder.AddOpenTelemetry(options =>
    {
        options.SetResourceBuilder(resource);
        options.AddOtlpExporter(o =>
        {
            o.Endpoint = new Uri($"{endpoint}/v1/logs");
            o.Protocol = OtlpExportProtocol.HttpProtobuf;
        });
    });
});
var logger = loggerFactory.CreateLogger("hello-world-csharp");

// -- Metrics ----------------------------------------------------------------
// A MeterProvider manages metrics. .NET uses System.Diagnostics.Metrics
// as its metrics API.
var meter = new Meter("hello-world-csharp");
var helloCounter = meter.CreateCounter<long>("hello.count", description: "Number of times the hello-world app has run");
var meterProvider = Sdk.CreateMeterProviderBuilder()
    .SetResourceBuilder(resource)
    .AddMeter("hello-world-csharp")
    .AddOtlpExporter(o =>
    {
        o.Endpoint = new Uri($"{endpoint}/v1/metrics");
        o.Protocol = OtlpExportProtocol.HttpProtobuf;
    })
    .Build()!;

// -- Application Logic ------------------------------------------------------

// A normal operation — creates a span with an info log.
void SayHello()
{
    using var activity = activitySource.StartActivity("say-hello");
    activity?.SetTag("greeting", "Hello, World!");
    // This log is emitted inside the span, so it carries the span's trace ID.
    // In Scout, you can jump to the trace from a log detail.
    logger.LogInformation("Hello, World!");
    helloCounter.Add(1);
}

// A degraded operation — creates a span with a warning log.
void CheckDiskSpace()
{
    using var activity = activitySource.StartActivity("check-disk-space");
    activity?.SetTag("disk.usage_percent", 92);
    // Warnings show up in Scout with a distinct severity level, making
    // them easy to filter and spot before they become errors.
    logger.LogWarning("Disk usage above 90%");
}

// A failed operation — creates a span with an error and exception.
void ParseConfig()
{
    using var activity = activitySource.StartActivity("parse-config");
    try
    {
        throw new InvalidOperationException("invalid config: missing 'database_url'");
    }
    catch (Exception ex)
    {
        // AddException attaches the stack trace to the span.
        // SetStatus marks the span as errored so it stands out in TraceX.
        activity?.AddException(ex);
        activity?.SetStatus(ActivityStatusCode.Error, ex.Message);
        logger.LogError(ex, "Failed to parse configuration");
    }
}

// -- Run --------------------------------------------------------------------

SayHello();
CheckDiskSpace();
ParseConfig();

// -- Shutdown ---------------------------------------------------------------
// Flush all buffered telemetry to the collector before exiting.
// Without this, the last batch of spans/logs/metrics may be lost.
tracerProvider.Dispose();
loggerFactory.Dispose();
meterProvider.Dispose();

Console.WriteLine("Done. Check Scout for your trace, log, and metric.");
