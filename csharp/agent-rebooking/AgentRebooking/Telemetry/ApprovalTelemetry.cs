using System.Diagnostics;
using System.Diagnostics.Metrics;
using AgentRebooking.Runs;

namespace AgentRebooking.Telemetry;

/// <summary>
/// The spans and instruments for the approval gate. An approval is two short spans and a
/// histogram point rather than one span held open across the human's thinking time: the
/// answer arrives on a different HTTP request, minutes later, and a span that outlives its
/// request makes batch export and tail sampling behave badly.
/// </summary>
/// <remarks>
/// Names the example owns carry a <c>base14.</c> prefix. They never sit bare and never sit
/// under <c>gen_ai.</c> or <c>mcp.</c>, which belong to the semantic conventions.
/// <see cref="ToolAttribute"/> is the exception that proves it: that one is semconv, and it
/// is used here with semconv's meaning.
/// </remarks>
public sealed class ApprovalTelemetry
{
    public const string RequestedSpanName = "base14.approval.requested";
    public const string DecidedSpanName = "base14.approval.decided";

    public const string WaitDurationInstrument = "base14.agent.approval.wait.duration";
    public const string CountInstrument = "base14.agent.approval.count";

    public const string ToolAttribute = "gen_ai.tool.name";
    public const string OutcomeAttribute = "base14.approval.outcome";
    public const string AmountAttribute = "base14.approval.amount";
    public const string LimitAttribute = "base14.approval.limit";
    public const string WaitSecondsAttribute = "base14.approval.wait_seconds";
    public const string RunIdAttribute = "base14.run.id";

    // A few seconds apart while an answer is still likely, minutes apart once it is not, and
    // one point past APPROVAL_TIMEOUT_SECONDS' default of 600 to separate a slow answer from
    // an expiry. Registered against the instrument by TelemetryRegistration.ConfigureMetrics;
    // the SDK's default boundaries stop being useful past 750 and teach nothing about this
    // example's own timeout.
    public static readonly double[] WaitDurationBucketBoundaries =
        [1, 5, 15, 30, 60, 120, 300, 600, 900];

    private readonly Histogram<double> _waitDuration;
    private readonly Counter<long> _count;

    public ApprovalTelemetry(Meter meter)
    {
        _waitDuration = meter.CreateHistogram<double>(
            WaitDurationInstrument,
            unit: "s",
            description: "Time an approval spent waiting for a human decision.");

        _count = meter.CreateCounter<long>(
            CountInstrument,
            unit: "{approval}",
            description: "Approval decisions by tool and outcome.");
    }

    /// <summary>
    /// Opens and closes the requested span where the handler decides a call needs a human,
    /// and hands back its context. The decided span happens on another request and links to
    /// that context, which is the only thread between the two.
    /// </summary>
    public ActivityContext Requested(ApprovalEntry entry)
    {
        using var activity = Sources.Activity.StartActivity($"{RequestedSpanName} {entry.Tool}");
        Describe(activity, entry);
        return activity?.Context ?? default;
    }

    /// <summary>
    /// The decision, wherever it came from: a human answering, or the sweep expiring the
    /// request. Parented to whatever is current, which is the answering request's span for an
    /// answer and nothing at all for an expiry.
    /// </summary>
    public void Decided(ApprovalEntry entry, ActivityContext requested, string outcome, TimeSpan waited)
    {
        var links = requested == default ? null : new[] { new ActivityLink(requested) };

        using (var activity = Sources.Activity.StartActivity(
            $"{DecidedSpanName} {entry.Tool}", ActivityKind.Internal, parentContext: default, links: links))
        {
            Describe(activity, entry);
            activity?.SetTag(OutcomeAttribute, outcome);
            activity?.SetTag(WaitSecondsAttribute, waited.TotalSeconds);
        }

        _waitDuration.Record(waited.TotalSeconds, Tags(entry.Tool, outcome));
        _count.Add(1, Tags(entry.Tool, outcome));
    }

    /// <summary>
    /// An under-limit call the app answered itself. Counted so the auto share of the spend is
    /// visible, and given no span: nobody waited, and a zero-length pair of spans per tool
    /// call would bury the ones a human was actually involved in.
    /// </summary>
    public void AutoApproved(ApprovalEntry entry) =>
        _count.Add(1, Tags(entry.Tool, ApprovalOutcomes.Auto));

    private static void Describe(Activity? activity, ApprovalEntry entry)
    {
        if (activity is null)
        {
            return;
        }

        activity.SetTag(ToolAttribute, entry.Tool);
        activity.SetTag(RunIdAttribute, entry.RunId);
        activity.SetTag(LimitAttribute, entry.Limit);

        // Null whenever the gate could not price the call server-side, which is itself a
        // reason a human was asked. Left off the span rather than written as an empty string.
        if (entry.Amount is { } amount)
        {
            activity.SetTag(AmountAttribute, amount);
        }
    }

    private static TagList Tags(string tool, string outcome) => new()
    {
        { ToolAttribute, tool },
        { OutcomeAttribute, outcome },
    };
}
