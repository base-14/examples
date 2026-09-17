using OpenTelemetry.Metrics;
using OpenTelemetry.Trace;

namespace AgentRebooking.Telemetry;

/// <summary>
/// The one place <see cref="Sources.TraceSourceNames"/> and <see cref="Sources.MeterNames"/>
/// are handed to a provider builder. Program.cs calls this when it builds the app's real
/// providers; TelemetryTests calls it again to build a bare provider over the same wiring, so
/// a test can prove the registration actually listens rather than re-typing the source list
/// and drifting from what the app does.
/// </summary>
internal static class TelemetryRegistration
{
    public static TracerProviderBuilder ConfigureTracing(TracerProviderBuilder tracing) => tracing
        .AddAspNetCoreInstrumentation(o => o.RecordException = true)
        .AddHttpClientInstrumentation()
        // The agent framework, MCP, Npgsql and the example's own source. Read
        // Telemetry/Sources.cs before changing this list: dropping the MCP name costs every
        // mcp.* attribute and the trace context hop into the server, with no error.
        .AddSource(Sources.TraceSourceNames);

    public static MeterProviderBuilder ConfigureMetrics(MeterProviderBuilder metrics) => metrics
        .AddAspNetCoreInstrumentation()
        .AddHttpClientInstrumentation()
        .AddRuntimeInstrumentation()
        // Every meter by name, the example's own included. A custom Meter that is not
        // registered here has its measurements silently dropped.
        .AddMeter(Sources.MeterNames)
        // See the boundaries themselves, next to the histogram, on ApprovalTelemetry.
        .AddView(ApprovalTelemetry.WaitDurationInstrument, new ExplicitBucketHistogramConfiguration
        {
            Boundaries = ApprovalTelemetry.WaitDurationBucketBoundaries,
        });
}
