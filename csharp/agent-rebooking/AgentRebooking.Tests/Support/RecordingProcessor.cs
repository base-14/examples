using System.Diagnostics;
using OpenTelemetry;

namespace AgentRebooking.Tests.Support;

/// <summary>
/// A <see cref="BaseProcessor{T}"/> that just remembers every activity a real
/// <c>TracerProvider</c> ends, so a test can prove the provider is actually listening rather
/// than asserting on the array of names handed to <c>AddSource</c>. No exporter package: the
/// SDK ships this base class itself.
/// </summary>
internal sealed class RecordingProcessor : BaseProcessor<Activity>
{
    private readonly Lock _sync = new();
    private readonly List<Activity> _ended = [];

    public IReadOnlyList<Activity> Ended
    {
        get
        {
            lock (_sync)
            {
                return [.. _ended];
            }
        }
    }

    public override void OnEnd(Activity data)
    {
        lock (_sync)
        {
            _ended.Add(data);
        }
    }
}
