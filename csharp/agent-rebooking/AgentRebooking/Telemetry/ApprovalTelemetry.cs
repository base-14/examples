using System.Diagnostics;
using System.Diagnostics.Metrics;
using AgentRebooking.Runs;

namespace AgentRebooking.Telemetry;

/// <summary>
/// The spans and instruments for the approval gate. An approval is two short spans and a
/// histogram point, not one span held open across the human's thinking time: the answer arrives
/// on a different request minutes later, and a span that outlives its request breaks batch
/// export and tail sampling. Names this example owns carry a <c>base14.</c> prefix;
/// <see cref="ToolAttribute"/> is semconv's, used with semconv's meaning.
/// </summary>
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

    // Human-scale, with one point past APPROVAL_TIMEOUT_SECONDS' default of 600 so a slow
    // answer reads differently from an expiry. Registered by TelemetryRegistration.
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
    /// Opens and closes the requested span, and hands back its context. The decided span
    /// happens on another request and links to it, which is the only thread between the two.
    /// </summary>
    public ActivityContext Requested(ApprovalEntry entry)
    {
        using var activity = Sources.Activity.StartActivity($"{RequestedSpanName} {entry.Tool}");
        Describe(activity, entry);
        return activity?.Context ?? default;
    }

    /// <summary>
    /// The decision, from a human answering or from the sweep expiring the request. Parented to
    /// whatever is current: the answering request's span, or nothing at all on an expiry.
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
    /// An under-limit call the app answered itself. Counted, not spanned: nobody waited, and a
    /// zero-length pair per tool call would bury the ones a human was involved in.
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

        // Null when the gate could not price the call, which is itself a reason a human was
        // asked. Left off the span rather than written empty.
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
