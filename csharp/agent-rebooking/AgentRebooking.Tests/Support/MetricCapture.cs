using System.Diagnostics.Metrics;

namespace AgentRebooking.Tests.Support;

internal sealed record RecordedMeasurement(string Instrument, double Value, IReadOnlyDictionary<string, object?> Tags);

/// <summary>
/// An in-memory metric reader for tests. Subscribes to one <see cref="Meter"/> directly
/// through <see cref="MeterListener"/>, so tests can assert on counter values and tags
/// without standing up an OpenTelemetry exporter.
/// </summary>
internal sealed class MetricCapture : IDisposable
{
    private readonly MeterListener _listener = new();
    private readonly List<RecordedMeasurement> _measurements = [];

    public MetricCapture(Meter meter)
    {
        _listener.InstrumentPublished = (instrument, listener) =>
        {
            if (instrument.Meter == meter)
            {
                listener.EnableMeasurementEvents(instrument);
            }
        };
        _listener.SetMeasurementEventCallback<long>((instrument, value, tags, _) =>
            Record(instrument.Name, value, tags));
        _listener.SetMeasurementEventCallback<double>((instrument, value, tags, _) =>
            Record(instrument.Name, value, tags));
        _listener.Start();
    }

    public IReadOnlyList<RecordedMeasurement> For(string instrumentName) =>
        _measurements.Where(m => m.Instrument == instrumentName).ToList();

    public int CountOf(string instrumentName) => For(instrumentName).Count;

    private void Record(string name, double value, ReadOnlySpan<KeyValuePair<string, object?>> tags)
    {
        var tagDict = new Dictionary<string, object?>();
        foreach (var tag in tags)
        {
            tagDict[tag.Key] = tag.Value;
        }

        _measurements.Add(new RecordedMeasurement(name, value, tagDict));
    }

    public void Dispose() => _listener.Dispose();
}
