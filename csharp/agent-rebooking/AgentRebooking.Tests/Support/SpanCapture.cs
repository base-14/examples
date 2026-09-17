using System.Diagnostics;

namespace AgentRebooking.Tests.Support;

/// <summary>
/// An in-memory span exporter for tests. Attaches an <see cref="ActivityListener"/> to a
/// named set of sources and keeps every activity that stops while it is alive, so tests can
/// assert on span names, parentage, links and attributes without an OpenTelemetry provider.
/// </summary>
/// <remarks>
/// Listeners are process-wide and xUnit runs test classes in parallel, so a capture sees
/// spans from whatever else is running. Filter by trace id, through
/// <see cref="InTraceOf"/>, rather than by span name alone.
/// </remarks>
internal sealed class SpanCapture : IDisposable
{
    private readonly ActivityListener _listener;
    private readonly Lock _sync = new();
    private readonly List<Activity> _spans = [];

    public SpanCapture(params string[] sourceNames)
    {
        _listener = new ActivityListener
        {
            ShouldListenTo = source => sourceNames.Contains(source.Name),
            Sample = (ref ActivityCreationOptions<ActivityContext> _) => ActivitySamplingResult.AllDataAndRecorded,
            ActivityStopped = activity =>
            {
                lock (_sync)
                {
                    _spans.Add(activity);
                }
            },
        };

        ActivitySource.AddActivityListener(_listener);
    }

    public IReadOnlyList<Activity> Spans
    {
        get
        {
            lock (_sync)
            {
                return [.. _spans];
            }
        }
    }

    /// <summary>Every captured span belonging to one trace, which is one test's own work.</summary>
    public IReadOnlyList<Activity> InTraceOf(ActivityContext context) =>
        [.. Spans.Where(span => span.TraceId == context.TraceId)];

    public void Dispose() => _listener.Dispose();
}

internal static class SpanAssert
{
    public static Activity Single(IEnumerable<Activity> spans, string operationName) =>
        Assert.Single(spans, span => span.OperationName == operationName);

    /// <summary>
    /// Reads one tag, tolerating the duplicate keys <see cref="Activity.AddTag"/> can leave
    /// behind. The MCP SDK enriches the outer <c>execute_tool</c> activity with AddTag while
    /// the agent framework has already set some of the same keys with SetTag, so a merged
    /// span can genuinely carry a key twice.
    /// </summary>
    public static IReadOnlyList<object?> TagValues(Activity span, string key) =>
        [.. span.TagObjects.Where(tag => tag.Key == key).Select(tag => tag.Value)];

    public static object? TagValue(Activity span, string key)
    {
        var values = TagValues(span, key);
        Assert.NotEmpty(values);
        Assert.All(values, value => Assert.Equal(values[0], value));
        return values[0];
    }
}
