using System.Diagnostics;
using System.Diagnostics.Metrics;
using AgentRebooking.Runs;
using AgentRebooking.Telemetry;
using AgentRebooking.Tests.Support;
using OpenTelemetry;
using OpenTelemetry.Metrics;
using OpenTelemetry.Trace;
using static AgentRebooking.Tests.Support.RunHarness;

namespace AgentRebooking.Tests;

/// <summary>
/// The spans and measurements a run produces, captured in memory. Everything here runs on
/// the scripted path with no model and no container, except that the MCP test opens a real
/// in-process MCP session, because the attributes and the parentage it asserts on are
/// produced by the MCP SDK and cannot be faked with a local function.
/// </summary>
/// <remarks>
/// Every capture listens on <see cref="Sources.TraceSourceNames"/> rather than on names written
/// out here, so dropping <see cref="Sources.ModelContextProtocol"/> fails the MCP test below
/// instead of losing half the app's trace in silence.
/// </remarks>
public class TelemetryTests
{
    private const string TestSourceName = "AgentRebooking.Tests";

    private const string ProbeActivityName = "tracer-registration-probe";

    private static readonly ActivitySource TestSource = new(TestSourceName);

    private static readonly string[] Listened = [.. Sources.TraceSourceNames, TestSourceName];

    [Fact]
    public async Task APendingApprovalOpensARequestedSpanInTheRunTrace()
    {
        using var spans = new SpanCapture(Listened);
        await using var harness = RunHarness.For(OverLimitBooking, OverLimitFlight);

        string runId;
        ActivityContext travellerRequest;
        using (var request = TestSource.StartActivity("POST /runs", ActivityKind.Server)!)
        {
            travellerRequest = request.Context;
            runId = harness.Store.Start("My booking is BK-1002 and my flight was cancelled.");
            await harness.Store.WhenSettledAsync(runId);
        }

        var requested = SpanAssert.Single(spans.InTraceOf(travellerRequest), "base14.approval.requested rebook");

        Assert.Equal(ActivityKind.Internal, requested.Kind);
        Assert.Equal("rebook", SpanAssert.TagValue(requested, "gen_ai.tool.name"));
        Assert.Equal(runId, SpanAssert.TagValue(requested, "base14.run.id"));
        Assert.Equal(620, Assert.IsType<int>(SpanAssert.TagValue(requested, "base14.approval.amount")));
        Assert.Equal(300, Assert.IsType<int>(SpanAssert.TagValue(requested, "base14.approval.limit")));

        // It ends where it starts. The human's thinking time is a histogram point, not a span
        // held open across two HTTP requests.
        Assert.True(requested.Duration < TimeSpan.FromSeconds(1));
    }

    /// <summary>
    /// The answer arrives on its own request and so on its own trace. The link is the only
    /// thing joining the two, which is why it is asserted on both ends.
    /// </summary>
    [Fact]
    public async Task AnsweringOpensADecidedSpanOnTheAnsweringRequestLinkedToTheRequestedOne()
    {
        using var spans = new SpanCapture(Listened);
        await using var harness = RunHarness.For(OverLimitBooking, OverLimitFlight);

        string runId;
        ActivityContext travellerRequest;
        using (var request = TestSource.StartActivity("POST /runs", ActivityKind.Server)!)
        {
            travellerRequest = request.Context;
            runId = harness.Store.Start("My booking is BK-1002 and my flight was cancelled.");
        }

        await harness.Store.WhenSettledAsync(runId);
        var approvalId = harness.Store.Get(runId)!.PendingApproval!.ApprovalId;
        harness.Clock.Advance(TimeSpan.FromSeconds(42));

        ActivityContext approvalRequest;
        using (var request = TestSource.StartActivity("POST /approvals/{id}", ActivityKind.Server)!)
        {
            approvalRequest = request.Context;
            await harness.Store.AnswerAsync(approvalId, approved: true);
        }

        await harness.Store.WhenSettledAsync(runId);

        Assert.NotEqual(travellerRequest.TraceId, approvalRequest.TraceId);

        var requested = SpanAssert.Single(spans.InTraceOf(travellerRequest), "base14.approval.requested rebook");
        var decided = SpanAssert.Single(spans.InTraceOf(approvalRequest), "base14.approval.decided rebook");

        Assert.Equal(approvalRequest.SpanId, decided.ParentSpanId);

        var link = Assert.Single(decided.Links);
        Assert.Equal(requested.TraceId, link.Context.TraceId);
        Assert.Equal(requested.SpanId, link.Context.SpanId);

        Assert.Equal("approved", SpanAssert.TagValue(decided, "base14.approval.outcome"));
        Assert.Equal(42d, Assert.IsType<double>(SpanAssert.TagValue(decided, "base14.approval.wait_seconds")));
        Assert.Equal("rebook", SpanAssert.TagValue(decided, "gen_ai.tool.name"));
        Assert.Equal(620, Assert.IsType<int>(SpanAssert.TagValue(decided, "base14.approval.amount")));
        Assert.Equal(300, Assert.IsType<int>(SpanAssert.TagValue(decided, "base14.approval.limit")));
    }

    /// <summary>The third decided-span outcome, over the same shape as the approved one.</summary>
    [Fact]
    public async Task RejectingOpensADecidedSpanAndCountsTheRejectedOutcome()
    {
        using var spans = new SpanCapture(Listened);
        await using var harness = RunHarness.For(OverLimitBooking, OverLimitFlight);

        var runId = harness.Store.Start("My booking is BK-1002 and my flight was cancelled.");
        await harness.Store.WhenSettledAsync(runId);
        var approvalId = harness.Store.Get(runId)!.PendingApproval!.ApprovalId;

        ActivityContext approvalRequest;
        using (var request = TestSource.StartActivity("POST /approvals/{id}", ActivityKind.Server)!)
        {
            approvalRequest = request.Context;
            await harness.Store.AnswerAsync(approvalId, approved: false);
        }

        await harness.Store.WhenSettledAsync(runId);

        var decided = SpanAssert.Single(spans.InTraceOf(approvalRequest), "base14.approval.decided rebook");
        Assert.Equal(ApprovalOutcomes.Rejected, SpanAssert.TagValue(decided, "base14.approval.outcome"));

        var counted = Assert.Single(harness.Metrics.For("base14.agent.approval.count"));
        Assert.Equal(ApprovalOutcomes.Rejected, counted.Tags["base14.approval.outcome"]);
    }

    /// <summary>
    /// An expiry reaches <c>DecideAsync</c> from the sweep, not a request, so its span roots its
    /// own trace.
    /// </summary>
    [Fact]
    public async Task AnExpiredApprovalStillGetsADecidedSpanAndACountedOutcome()
    {
        using var spans = new SpanCapture(Listened);
        var options = Defaults with { ApprovalTimeoutSeconds = 60 };
        await using var harness = RunHarness.For(OverLimitBooking, OverLimitFlight, options);

        string runId;
        ActivityContext travellerRequest;
        using (var request = TestSource.StartActivity("POST /runs", ActivityKind.Server)!)
        {
            travellerRequest = request.Context;
            runId = harness.Store.Start("My booking is BK-1002 and my flight was cancelled.");
        }

        await harness.Store.WhenSettledAsync(runId);
        harness.Clock.Advance(TimeSpan.FromSeconds(90));
        await harness.Store.SweepAsync();
        await harness.Store.WhenSettledAsync(runId);

        var requested = SpanAssert.Single(spans.InTraceOf(travellerRequest), "base14.approval.requested rebook");
        var decided = Assert.Single(
            spans.Spans,
            span => span.OperationName == "base14.approval.decided rebook"
                && span.Links.Any(link => link.Context.SpanId == requested.SpanId));

        Assert.Equal(default, decided.ParentSpanId);
        Assert.Equal("expired", SpanAssert.TagValue(decided, "base14.approval.outcome"));
        Assert.Equal(90d, Assert.IsType<double>(SpanAssert.TagValue(decided, "base14.approval.wait_seconds")));

        var counted = Assert.Single(harness.Metrics.For("base14.agent.approval.count"));
        Assert.Equal("expired", counted.Tags["base14.approval.outcome"]);
    }

    /// <summary>
    /// An answer on the handover-failure branch is still an answer. Outcomes are written at two
    /// call sites, and only one of them opening a decided span would lose this one.
    /// </summary>
    [Fact]
    public async Task ADecisionThatFailsTheRunOnTheStreamHandoverIsStillMeasured()
    {
        using var spans = new SpanCapture(Listened);
        var logger = new PausingLogger<RunStore>(RunStore.PendingApprovalLogMessage);
        await using var harness = RunHarness.For(
            OverLimitBooking, OverLimitFlight, logger: logger, passHandover: TimeSpan.FromMilliseconds(50));

        string runId;
        ActivityContext travellerRequest;
        using (var request = TestSource.StartActivity("POST /runs", ActivityKind.Server)!)
        {
            travellerRequest = request.Context;
            runId = harness.Store.Start("My booking is BK-1002 and my flight was cancelled.");
        }

        await logger.Reached.WaitAsync(TimeSpan.FromSeconds(10));
        var approvalId = harness.Store.Get(runId)!.PendingApproval!.ApprovalId;
        harness.Clock.Advance(TimeSpan.FromSeconds(15));

        ActivityContext approvalRequest;
        using (var request = TestSource.StartActivity("POST /approvals/{id}", ActivityKind.Server)!)
        {
            approvalRequest = request.Context;
            await harness.Store.AnswerAsync(approvalId, approved: true).WaitAsync(TimeSpan.FromSeconds(10));
        }

        Assert.Equal(RunStates.Failed, harness.Store.Get(runId)!.State);

        var decided = SpanAssert.Single(spans.InTraceOf(approvalRequest), "base14.approval.decided rebook");
        Assert.Equal(ApprovalOutcomes.Approved, SpanAssert.TagValue(decided, "base14.approval.outcome"));

        var requested = SpanAssert.Single(spans.InTraceOf(travellerRequest), "base14.approval.requested rebook");
        Assert.Equal(requested.SpanId, Assert.Single(decided.Links).Context.SpanId);

        var wait = Assert.Single(harness.Metrics.For("base14.agent.approval.wait.duration"));
        Assert.Equal(15d, wait.Value);
        Assert.Equal(ApprovalOutcomes.Approved, wait.Tags["base14.approval.outcome"]);

        logger.Release();
        await harness.Store.WhenSettledAsync(runId);
    }

    // --- error status, the rule written out at RunStore.Fail ------------------

    /// <summary>
    /// Recorded from the sweeper's thread, where nothing is current, so the record's published
    /// activity is the only way the run's span can carry the failure.
    /// </summary>
    [Fact]
    public async Task ARunTimeoutMarksTheRunSpanErrorFromTheSweepersThread()
    {
        using var spans = new SpanCapture(Listened);

        // Held on its first turn, so the sweep lands with the pass genuinely inside
        // base14.agent.run rather than racing the task that starts it.
        var paused = new PausingChatClient(
            new ScriptedAgentChatClient(Script(UnderLimitBooking, UnderLimitFlight)), pauseOnTurn: 1);
        var options = Defaults with { RunTimeoutSeconds = 30 };
        await using var harness = RunHarness.For(UnderLimitBooking, UnderLimitFlight, options, paused);

        string runId;
        ActivityContext travellerRequest;
        using (var request = TestSource.StartActivity("POST /runs", ActivityKind.Server)!)
        {
            travellerRequest = request.Context;
            runId = harness.Store.Start("My booking is BK-1001 and my flight was cancelled.");
            await paused.Reached.WaitAsync(TimeSpan.FromSeconds(10));

            harness.Clock.Advance(TimeSpan.FromSeconds(31));
            await harness.Store.SweepAsync();
            await harness.Store.WhenSettledAsync(runId).WaitAsync(TimeSpan.FromSeconds(10));
        }

        paused.Release();

        var run = SpanAssert.Single(spans.InTraceOf(travellerRequest), "base14.agent.run");
        Assert.Equal(ActivityStatusCode.Error, run.Status);
        Assert.Equal("the run exceeded RUN_TIMEOUT_SECONDS", run.StatusDescription);
    }

    /// <summary>
    /// A failure recorded on the approver's request lands on the run's span, not the approver's.
    /// Drives the handover-past-the-bound branch and asserts both halves.
    /// </summary>
    [Fact]
    public async Task AFailureOnTheApproversRequestMarksTheRunSpanAndNotTheApproversOwn()
    {
        using var spans = new SpanCapture(Listened);
        var logger = new PausingLogger<RunStore>(RunStore.PendingApprovalLogMessage);
        await using var harness = RunHarness.For(
            OverLimitBooking, OverLimitFlight, logger: logger, passHandover: TimeSpan.FromMilliseconds(50));

        string runId;
        ActivityContext travellerRequest;
        using (var request = TestSource.StartActivity("POST /runs", ActivityKind.Server)!)
        {
            travellerRequest = request.Context;
            runId = harness.Store.Start("My booking is BK-1002 and my flight was cancelled.");
        }

        await logger.Reached.WaitAsync(TimeSpan.FromSeconds(10));
        var approvalId = harness.Store.Get(runId)!.PendingApproval!.ApprovalId;

        ActivityContext approvalRequest;
        using (var request = TestSource.StartActivity("POST /approvals/{id}", ActivityKind.Server)!)
        {
            approvalRequest = request.Context;
            await harness.Store.AnswerAsync(approvalId, approved: true).WaitAsync(TimeSpan.FromSeconds(10));
        }

        logger.Release();
        await harness.Store.WhenSettledAsync(runId).WaitAsync(TimeSpan.FromSeconds(10));

        Assert.Equal(RunStates.Failed, harness.Store.Get(runId)!.State);

        var run = SpanAssert.Single(spans.InTraceOf(travellerRequest), "base14.agent.run");
        Assert.Equal(ActivityStatusCode.Error, run.Status);
        Assert.Contains("did not release its stream", run.StatusDescription!);

        var approverSpans = spans.InTraceOf(approvalRequest);
        Assert.Contains(approverSpans, span => span.OperationName == "POST /approvals/{id}");
        Assert.All(approverSpans, span => Assert.Equal(ActivityStatusCode.Unset, span.Status));
    }

    /// <summary>
    /// A human declining is the gate working, not an incident: the outcome attribute carries it
    /// and every span stays Unset.
    /// </summary>
    [Fact]
    public async Task ARejectedApprovalLeavesEverySpanOfTheRunUnset()
    {
        using var spans = new SpanCapture(Listened);
        await using var harness = RunHarness.For(OverLimitBooking, OverLimitFlight);

        string runId;
        ActivityContext travellerRequest;
        using (var request = TestSource.StartActivity("POST /runs", ActivityKind.Server)!)
        {
            travellerRequest = request.Context;
            runId = harness.Store.Start("My booking is BK-1002 and my flight was cancelled.");
            await harness.Store.WhenSettledAsync(runId);
        }

        var approvalId = harness.Store.Get(runId)!.PendingApproval!.ApprovalId;

        ActivityContext approvalRequest;
        using (var request = TestSource.StartActivity("POST /approvals/{id}", ActivityKind.Server)!)
        {
            approvalRequest = request.Context;
            await harness.Store.AnswerAsync(approvalId, approved: false);
        }

        await harness.Store.WhenSettledAsync(runId);

        var run = harness.Store.Get(runId)!;
        Assert.Equal(RunStates.Completed, run.State);
        Assert.Equal(ApprovalOutcomes.Rejected, run.Outcome);

        var decided = SpanAssert.Single(spans.InTraceOf(approvalRequest), "base14.approval.decided rebook");
        Assert.Equal(ApprovalOutcomes.Rejected, SpanAssert.TagValue(decided, "base14.approval.outcome"));

        var both = (IReadOnlyList<Activity>)
            [.. spans.InTraceOf(travellerRequest), .. spans.InTraceOf(approvalRequest)];
        Assert.Contains(both, span => span.OperationName == "base14.agent.run");
        Assert.All(both, span => Assert.Equal(ActivityStatusCode.Unset, span.Status));
    }

    /// <summary>
    /// One auto-approved run and one a human approved, over one meter. The counter sees both;
    /// the histogram sees only the one somebody waited on.
    /// </summary>
    [Fact]
    public async Task TheCounterSeesAutoAndApprovedButOnlyTheHumanOneReachesTheWaitHistogram()
    {
        using var spans = new SpanCapture(Listened);
        var client = new ScriptedAgentChatClient(
        [
            .. Script(UnderLimitBooking, UnderLimitFlight),
            .. Script(OverLimitBooking, OverLimitFlight),
        ]);
        await using var harness = RunHarness.For(OverLimitBooking, OverLimitFlight, chatClient: client);

        ActivityContext travellerRequest;
        string autoRunId;
        using (var request = TestSource.StartActivity("POST /runs", ActivityKind.Server)!)
        {
            travellerRequest = request.Context;
            autoRunId = harness.Store.Start("My booking is BK-1001 and my flight was cancelled.");
            await harness.Store.WhenSettledAsync(autoRunId);
        }

        Assert.Equal(ApprovalOutcomes.Auto, harness.Store.Get(autoRunId)!.Outcome);

        // No span of either kind for the call the app answered itself.
        Assert.DoesNotContain(
            spans.InTraceOf(travellerRequest),
            span => span.OperationName.StartsWith("base14.approval.", StringComparison.Ordinal));

        var humanRunId = harness.Store.Start("My booking is BK-1002 and my flight was cancelled.");
        await harness.Store.WhenSettledAsync(humanRunId);
        harness.Clock.Advance(TimeSpan.FromSeconds(90));
        await harness.Store.AnswerAsync(
            harness.Store.Get(humanRunId)!.PendingApproval!.ApprovalId, approved: true);
        await harness.Store.WhenSettledAsync(humanRunId);

        var wait = Assert.Single(harness.Metrics.For("base14.agent.approval.wait.duration"));
        Assert.Equal(90d, wait.Value);
        Assert.Equal("rebook", wait.Tags["gen_ai.tool.name"]);
        Assert.Equal(ApprovalOutcomes.Approved, wait.Tags["base14.approval.outcome"]);

        var counted = harness.Metrics.For("base14.agent.approval.count");
        Assert.Equal(2, counted.Count);
        Assert.All(counted, measurement => Assert.Equal("rebook", measurement.Tags["gen_ai.tool.name"]));
        Assert.Equal(
            [ApprovalOutcomes.Auto, ApprovalOutcomes.Approved],
            counted.Select(measurement => measurement.Tags["base14.approval.outcome"]));
    }

    /// <summary>
    /// OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT puts the traveller's words on exported
    /// spans, so it defaults to off and only this test turns it on.
    /// </summary>
    [Fact]
    public async Task CaptureMessageContentControlsWhetherTheChatSpanCarriesTheTravellersWords()
    {
        const string message = "My booking is BK-1001 and my flight was cancelled.";

        using (var spans = new SpanCapture(Listened))
        {
            await using var harness = RunHarness.For(UnderLimitBooking, UnderLimitFlight);
            using var request = TestSource.StartActivity("POST /runs", ActivityKind.Server)!;
            var runId = harness.Store.Start(message);
            await harness.Store.WhenSettledAsync(runId);

            var chat = spans.InTraceOf(request.Context).First(span => span.OperationName == "chat");
            Assert.Empty(SpanAssert.TagValues(chat, "gen_ai.input.messages"));
        }

        using (var spans = new SpanCapture(Listened))
        {
            await using var harness = RunHarness.For(
                UnderLimitBooking, UnderLimitFlight, captureMessageContent: true);
            using var request = TestSource.StartActivity("POST /runs", ActivityKind.Server)!;
            var runId = harness.Store.Start(message);
            await harness.Store.WhenSettledAsync(runId);

            var chat = spans.InTraceOf(request.Context).First(span => span.OperationName == "chat");
            var content = Assert.IsType<string>(SpanAssert.TagValue(chat, "gen_ai.input.messages"));
            Assert.Contains(message, content, StringComparison.Ordinal);
        }
    }

    /// <summary>
    /// There is no MCP client span for a tool call: the SDK hangs the <c>mcp.*</c> attributes on
    /// the outer <c>execute_tool</c> activity and parents the server span to it. A request with
    /// no outer tool span, such as <c>tools/list</c>, does get one, asserted at the end.
    /// </summary>
    [Fact]
    public async Task AToolCallPutsTheMcpAttributesOnExecuteToolAndParentsTheServerSpanToIt()
    {
        using var spans = new SpanCapture(Listened);

        // The app opens its session at startup, in a trace of its own. Opening it ahead of
        // "POST /runs" here keeps the span tree the shape the app produces.
        ActivityContext startup;
        StubMcpSession mcp;
        using (var startupActivity = TestSource.StartActivity("mcp session start")!)
        {
            startup = startupActivity.Context;
            mcp = await StubMcpSession.StartAsync();
        }

        await using var mcpSession = mcp;
        using var request = TestSource.StartActivity("POST /runs", ActivityKind.Server)!;

        await using var harness = RunHarness.For(
            UnderLimitBooking, UnderLimitFlight, agentTools: mcp.Tools);

        // Built over the MCP session above, never over FakeRebookingTools, so asking for Tools
        // has to say so rather than read as "not invoked".
        Assert.Throws<InvalidOperationException>(() => harness.Tools);

        var runId = harness.Store.Start("My booking is BK-1001 and my flight was cancelled.");
        await harness.Store.WhenSettledAsync(runId);
        Assert.Equal(RunStates.Completed, harness.Store.Get(runId)!.State);

        var mine = spans.InTraceOf(request.Context);

        var executeTool = SpanAssert.Single(mine, "execute_tool lookup_booking");
        Assert.Equal("lookup_booking", SpanAssert.TagValue(executeTool, "gen_ai.tool.name"));
        Assert.Equal("tools/call", SpanAssert.TagValue(executeTool, "mcp.method.name"));
        Assert.NotNull(SpanAssert.TagValue(executeTool, "mcp.session.id"));
        Assert.Equal("pipe", SpanAssert.TagValue(executeTool, "network.transport"));

        // The merged span carries these twice: the agent framework sets them, then the MCP SDK
        // appends its own with AddTag rather than SetTag. Same values, but a backend that renders
        // attributes as a list shows each key twice.
        Assert.Equal(2, SpanAssert.TagValues(executeTool, "gen_ai.tool.name").Count);
        Assert.Equal(2, SpanAssert.TagValues(executeTool, "gen_ai.operation.name").Count);
        Assert.Single(SpanAssert.TagValues(executeTool, "mcp.method.name"));

        // One span, not two: the client side of this call is the execute_tool span above.
        var serverSpan = SpanAssert.Single(mine, "tools/call lookup_booking");
        Assert.Equal(ActivityKind.Server, serverSpan.Kind);
        Assert.Equal(executeTool.SpanId, serverSpan.ParentSpanId);
        Assert.Equal(executeTool.TraceId, serverSpan.TraceId);

        // The session's own tools/list, from opening it above, not from the run.
        var toolsList = spans.InTraceOf(startup).Where(span => span.OperationName == "tools/list").ToList();
        Assert.Equal(2, toolsList.Count);
        Assert.Contains(toolsList, span => span.Kind == ActivityKind.Client);
        Assert.Contains(toolsList, span => span.Kind == ActivityKind.Server);
        Assert.DoesNotContain(mine, span => span.OperationName == "tools/list");
    }

    [Fact]
    public void TheRegisteredSourcesAndMetersAreTheOnesTheDesignNames()
    {
        Assert.Equal(
            [
                "AgentRebooking",
                "Experimental.Microsoft.Agents.AI",
                "Experimental.ModelContextProtocol",
                "Npgsql",
            ],
            Sources.TraceSourceNames);

        Assert.Equal(Sources.TraceSourceNames, Sources.MeterNames);

        // Gated behind a builder method the handoff builder does not expose at 1.21.0.
        Assert.DoesNotContain("Microsoft.Agents.AI.Workflows", Sources.TraceSourceNames);
    }

    /// <summary>
    /// The test above pins the array's contents; this one proves it reaches a provider, through
    /// the same <see cref="TelemetryRegistration"/> method Program.cs calls.
    /// </summary>
    [Fact]
    public void TheAppsTracerProviderActuallyListensOnEveryRegisteredSource()
    {
        var recorder = new RecordingProcessor();

        using var provider = TelemetryRegistration
            .ConfigureTracing(Sdk.CreateTracerProviderBuilder())
            .AddProcessor(recorder)
            .Build();

        foreach (var name in Sources.TraceSourceNames)
        {
            using var source = new ActivitySource(name);
            using (var probe = source.StartActivity(ProbeActivityName))
            {
                Assert.NotNull(probe);
            }
        }

        // Test classes run in parallel and this provider carries the AspNetCore instrumentation
        // too, so match on the probe name.
        var heard = recorder.Ended
            .Where(activity => activity.OperationName == ProbeActivityName)
            .Select(activity => activity.Source.Name)
            .ToHashSet();
        Assert.Equal(Sources.TraceSourceNames.ToHashSet(), heard);
    }

    /// <summary>
    /// The SDK's default boundaries stop being useful past 750 seconds and
    /// APPROVAL_TIMEOUT_SECONDS defaults to 600, so the view is not optional.
    /// </summary>
    [Fact]
    public void TheApprovalWaitHistogramIsViewedWithHumanScaleBucketBoundaries()
    {
        using var meter = new Meter(Sources.AgentRebooking);
        var telemetry = new ApprovalTelemetry(meter);
        var exporter = new RecordingMetricExporter();
        IReadOnlyList<Metric> exported;

        using (var reader = new BaseExportingMetricReader(exporter))
        using (var provider = TelemetryRegistration
            .ConfigureMetrics(Sdk.CreateMeterProviderBuilder())
            .AddReader(reader)
            .Build())
        {
            telemetry.Decided(
                new ApprovalEntry(
                    "ap-view-test", "run-view-test", "rebook", "BK-1001", null, 620, 300,
                    "over limit", ApprovalOutcomes.Approved, DateTimeOffset.UtcNow, DateTimeOffset.UtcNow),
                default, ApprovalOutcomes.Approved, TimeSpan.FromSeconds(42));

            reader.Collect();

            // Before the provider disposes: shutdown forces one more collect of its own.
            exported = exporter.Exported;
        }

        // AddMeter matches by name, so parallel test classes add points and the instrument can
        // be exported more than once. Assert the boundaries everywhere, not on a single point.
        var points = 0;
        foreach (var histogram in exported.Where(
            metric => metric.Name == ApprovalTelemetry.WaitDurationInstrument))
        {
            foreach (var point in histogram.GetMetricPoints())
            {
                points++;

                List<double> boundaries = [];
                foreach (var bucket in point.GetHistogramBuckets())
                {
                    if (!double.IsPositiveInfinity(bucket.ExplicitBound))
                    {
                        boundaries.Add(bucket.ExplicitBound);
                    }
                }

                Assert.Equal(ApprovalTelemetry.WaitDurationBucketBoundaries, boundaries);
            }
        }

        Assert.True(points > 0, "the histogram exported no points");
    }
}
