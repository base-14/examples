using OpenTelemetry;
using OpenTelemetry.Metrics;

namespace AgentRebooking.Tests.Support;

/// <summary>
/// A <see cref="BaseExporter{T}"/> that copies every exported <see cref="Metric"/> it sees, so
/// a test can inspect a real <c>MeterProvider</c>'s output -- bucket boundaries included --
/// without pulling in an exporter package the test project does not otherwise need.
/// </summary>
internal sealed class RecordingMetricExporter : BaseExporter<Metric>
{
    private readonly Lock _sync = new();
    private readonly List<Metric> _exported = [];

    public IReadOnlyList<Metric> Exported
    {
        get
        {
            lock (_sync)
            {
                return [.. _exported];
            }
        }
    }

    public override ExportResult Export(in Batch<Metric> batch)
    {
        lock (_sync)
        {
            foreach (var metric in batch)
            {
                _exported.Add(metric);
            }
        }

        return ExportResult.Success;
    }
}
