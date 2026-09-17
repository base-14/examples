namespace AgentRebooking.Runs;

/// <summary>
/// The four run states the design's <c>GET /runs/{id}</c> returns. Strings rather than an
/// enum so the wire shape and the code agree without a mapping layer.
/// </summary>
public static class RunStates
{
    public const string Running = "running";
    public const string PendingApproval = "pending_approval";
    public const string Completed = "completed";
    public const string Failed = "failed";
}

public static class ApprovalOutcomes
{
    /// <summary>Waiting for a human.</summary>
    public const string Pending = "pending";

    /// <summary>Under the limit, so the app answered the workflow itself.</summary>
    public const string Auto = "auto";

    public const string Approved = "approved";
    public const string Rejected = "rejected";

    /// <summary>Not answered within APPROVAL_TIMEOUT_SECONDS. Treated as a rejection.</summary>
    public const string Expired = "expired";
}

public sealed record ToolCallEntry(string Tool, string Arguments, DateTimeOffset At);

public sealed record ApprovalEntry(
    string ApprovalId,
    string RunId,
    string Tool,
    string? BookingRef,
    string? OfferId,
    int? Amount,
    int Limit,
    string Reason,
    string Outcome,
    DateTimeOffset RequestedAt,
    DateTimeOffset? DecidedAt);

public sealed record RunSnapshot(
    string RunId,
    string State,
    string? Outcome,
    string? Reply,
    string? Error,
    IReadOnlyList<ToolCallEntry> ToolCalls,
    IReadOnlyList<ApprovalEntry> Approvals)
{
    public ApprovalEntry? PendingApproval => State == RunStates.PendingApproval
        ? Approvals.FirstOrDefault(approval => approval.Outcome == ApprovalOutcomes.Pending)
        : null;
}

/// <param name="ApprovalTimeoutSeconds">APPROVAL_TIMEOUT_SECONDS, after which a pending approval expires.</param>
/// <param name="RunTimeoutSeconds">RUN_TIMEOUT_SECONDS, after which a still-running run fails.</param>
/// <param name="RunTtlSeconds">RUN_TTL_SECONDS, after which a settled run is evicted.</param>
public sealed record RunStoreOptions(
    int ApprovalTimeoutSeconds,
    int RunTimeoutSeconds,
    int RunTtlSeconds);

public enum AnswerResult
{
    Accepted,

    /// <summary>No approval with that id, in any run.</summary>
    NotFound,

    /// <summary>Already answered, expired, or its run has finished. First answer wins.</summary>
    Conflict,
}
