using System.Diagnostics.Metrics;
using AgentRebooking.Agents;
using AgentRebooking.Runs;
using AgentRebooking.Telemetry;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace AgentRebooking.Tests.Support;

/// <summary>
/// One run store wired to the whole handoff workflow with a scripted chat client, local
/// stand-ins for the MCP tools and a clock the test moves by hand. No model and no
/// container, so anything built on this runs anywhere.
/// </summary>
/// <param name="Meter">
/// The meter <see cref="Metrics"/> listens on and the store's own
/// <see cref="ApprovalTelemetry"/> writes to. One per harness, so measurements from tests
/// running in parallel cannot reach each other.
/// </param>
internal sealed record RunHarness(
    RunStore Store,
    TestTimeProvider Clock,
    Meter Meter,
    MetricCapture Metrics) : IAsyncDisposable
{
    /// <summary>Backs <see cref="Tools"/>; null when the harness was built over <c>agentTools</c>.</summary>
    private FakeRebookingTools? ToolsOrNull { get; init; }

    /// <summary>
    /// The local fakes the rebooking agent was built from. Throws rather than reading as
    /// "not invoked" when the harness was built with <c>agentTools</c> instead -- an MCP-backed
    /// harness never wires these, and a caller asking about them almost always means the
    /// other harness.
    /// </summary>
    public FakeRebookingTools Tools => ToolsOrNull
        ?? throw new InvalidOperationException(
            "This harness was built with agentTools, so FakeRebookingTools was never wired " +
            "and was never invoked either. Check the tools the harness actually used instead.");

    public const string UnderLimitBooking = "BK-1001";
    public const string UnderLimitFlight = "FL-201";
    public const string OverLimitBooking = "BK-1002";
    public const string OverLimitFlight = "FL-301";
    public const string FinalReply = "I have dealt with your booking.";

    /// <summary>
    /// The gate's limit. It reaches <see cref="ApprovalGate"/> directly, the way Program.cs
    /// passes it, rather than through <see cref="RunStoreOptions"/>, which RunStore does not
    /// read it from.
    /// </summary>
    public const int ApprovalLimit = 300;

    public static readonly RunStoreOptions Defaults = new(
        ApprovalTimeoutSeconds: 600, RunTimeoutSeconds: 300, RunTtlSeconds: 3600);

    /// <summary>
    /// The four assistant turns a run takes: triage hands off, rebooking looks the booking
    /// up, rebooks, then replies. The rebook turn is the one that pauses for approval, so
    /// the reply is turn four and the only turn a resume runs.
    /// </summary>
    public static ChatMessage[] Script(string bookingRef, string flightId) =>
    [
        ScriptedAgentChatClient.ToolCall(
            AgentSetup.HandoffToolName, ("reasonForHandoff", "the traveller's flight was cancelled")),
        ScriptedAgentChatClient.ToolCall("lookup_booking", ("booking_ref", bookingRef)),
        ScriptedAgentChatClient.ToolCall("rebook", ("booking_ref", bookingRef), ("flight_id", flightId)),
        ScriptedAgentChatClient.Reply(FinalReply),
    ];

    /// <param name="agentTools">
    /// The tools the rebooking agent is built from, when they have to be something other
    /// than the local fakes -- a real MCP session, for the telemetry of that hop. Supplying
    /// this means the harness never builds <see cref="FakeRebookingTools"/> at all, so
    /// <see cref="Tools"/> throws rather than reporting calls that never happened.
    /// </param>
    /// <param name="captureMessageContent">
    /// Threaded straight to <see cref="AgentSetup.BuildWorkflow"/>. False by default, which
    /// keeps every existing test's behaviour unchanged.
    /// </param>
    public static RunHarness For(
        string bookingRef,
        string flightId,
        RunStoreOptions? options = null,
        IChatClient? chatClient = null,
        ILogger<RunStore>? logger = null,
        TimeSpan? passHandover = null,
        IEnumerable<AITool>? agentTools = null,
        bool captureMessageContent = false)
    {
        var effective = options ?? Defaults;
        var tools = agentTools is null ? new FakeRebookingTools() : null;
        var client = chatClient ?? new ScriptedAgentChatClient(Script(bookingRef, flightId));
        var clock = new TestTimeProvider();
        var meter = new Meter(Sources.AgentRebooking);
        var metrics = new MetricCapture(meter);

        var store = new RunStore(
            () => AgentSetup.BuildWorkflow(client, agentTools ?? tools!.Tools, captureMessageContent),
            new ApprovalGate(new SeedPriceLookup(), ApprovalLimit),
            effective,
            new ApprovalTelemetry(meter),
            clock,
            logger ?? NullLogger<RunStore>.Instance)
        {
            PassHandover = passHandover ?? TimeSpan.FromSeconds(5),
        };

        return new RunHarness(store, clock, meter, metrics) { ToolsOrNull = tools };
    }

    public async ValueTask DisposeAsync()
    {
        await Store.DisposeAsync();
        Metrics.Dispose();
        Meter.Dispose();
    }
}
