using OpenTelemetry.Metrics;
using OpenTelemetry.Trace;

namespace AgentRebooking.Telemetry;

/// <summary>
/// The one place <see cref="Sources.TraceSourceNames"/> and <see cref="Sources.MeterNames"/> are
/// handed to a provider builder. Program.cs and TelemetryTests both call it, so the tests assert
/// on the app's own wiring rather than a re-typed copy of it.
/// </summary>
internal static class TelemetryRegistration
{
    public static TracerProviderBuilder ConfigureTracing(TracerProviderBuilder tracing) => tracing
        .AddAspNetCoreInstrumentation(o => o.RecordException = true)
        .AddHttpClientInstrumentation()
        // Dropping the MCP name here silently costs every mcp.* attribute and the trace
        // context hop into the server. See Telemetry/Sources.cs.
        .AddSource(Sources.TraceSourceNames);

    public static MeterProviderBuilder ConfigureMetrics(MeterProviderBuilder metrics) => metrics
        .AddAspNetCoreInstrumentation()
        .AddHttpClientInstrumentation()
        .AddRuntimeInstrumentation()
        // AddMeter matches by name, not by instance, and a mismatch drops measurements silently.
        .AddMeter(Sources.MeterNames)
        .AddView(ApprovalTelemetry.WaitDurationInstrument, new ExplicitBucketHistogramConfiguration
        {
            Boundaries = ApprovalTelemetry.WaitDurationBucketBoundaries,
        });
}
