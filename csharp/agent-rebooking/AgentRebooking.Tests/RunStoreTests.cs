using System.Diagnostics;
using AgentRebooking.Agents;
using AgentRebooking.Runs;
using AgentRebooking.Telemetry;
using AgentRebooking.Tests.Support;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using static AgentRebooking.Tests.Support.RunHarness;

namespace AgentRebooking.Tests;

/// <summary>
/// Drives the whole handoff workflow, approval pause and resume with a scripted in-process
/// chat client and local stand-ins for the MCP tools. No model and no container, so these
/// run anywhere.
/// </summary>
public class RunStoreTests
{
    private const string TestSourceName = "AgentRebooking.Tests";

    private static readonly ActivitySource TestSource = new(TestSourceName);

    [Fact]
    public async Task UnderLimitRunCompletesWithoutWaitingForAHuman()
    {
        await using var harness = RunHarness.For(UnderLimitBooking, UnderLimitFlight);

        var runId = harness.Store.Start("My booking is BK-1001 and my flight to Berlin was cancelled.");
        await harness.Store.WhenSettledAsync(runId);

        var run = harness.Store.Get(runId)!;
        Assert.Equal(RunStates.Completed, run.State);
        Assert.Null(run.PendingApproval);
        Assert.Equal(ApprovalOutcomes.Auto, run.Outcome);
        Assert.Contains(run.ToolCalls, call => call.Tool == "rebook");
        Assert.True(harness.Tools.WasInvoked("rebook"));
        Assert.Equal(FinalReply, run.Reply);
    }

    /// <summary>
    /// The handoff only happens when the injected tool is called by the name the framework
    /// actually gives it. If that name ever changes this is the test that says so.
    /// </summary>
    [Fact]
    public async Task TheHandoffToolCallIsInTheToolLog()
    {
        await using var harness = RunHarness.For(UnderLimitBooking, UnderLimitFlight);

        var runId = harness.Store.Start("My flight was cancelled.");
        await harness.Store.WhenSettledAsync(runId);

        var run = harness.Store.Get(runId)!;
        Assert.Contains(run.ToolCalls, call => call.Tool == AgentSetup.HandoffToolName);
        Assert.Equal("handoff_to_1", AgentSetup.HandoffToolName);
    }

    [Fact]
    public async Task OverLimitRunStopsAtPendingApprovalWithTheServerSidePrice()
    {
        await using var harness = RunHarness.For(OverLimitBooking, OverLimitFlight);

        var runId = harness.Store.Start("My booking is BK-1002 and my flight to New York was cancelled.");
        await harness.Store.WhenSettledAsync(runId);

        var run = harness.Store.Get(runId)!;
        Assert.Equal(RunStates.PendingApproval, run.State);

        var pending = run.PendingApproval!;
        Assert.Equal("rebook", pending.Tool);
        Assert.Equal(620, pending.Amount);
        Assert.Equal(300, pending.Limit);
        Assert.False(harness.Tools.WasInvoked("rebook"));

        Assert.Equal(pending.ApprovalId, Assert.Single(harness.Store.ListPendingApprovals()).ApprovalId);
    }

    [Fact]
    public async Task ApprovingRunsTheToolAndCompletesTheRun()
    {
        await using var harness = RunHarness.For(OverLimitBooking, OverLimitFlight);
        var runId = harness.Store.Start("My booking is BK-1002 and my flight was cancelled.");
        await harness.Store.WhenSettledAsync(runId);
        var approvalId = harness.Store.Get(runId)!.PendingApproval!.ApprovalId;

        var result = await harness.Store.AnswerAsync(approvalId, approved: true);
        await harness.Store.WhenSettledAsync(runId);

        Assert.Equal(AnswerResult.Accepted, result);
        var run = harness.Store.Get(runId)!;
        Assert.Equal(RunStates.Completed, run.State);
        Assert.Equal(ApprovalOutcomes.Approved, run.Outcome);
        Assert.Null(run.PendingApproval);
        Assert.True(harness.Tools.WasInvoked("rebook"));
        Assert.Equal(FinalReply, run.Reply);
    }

    [Fact]
    public async Task RejectingLeavesTheBookingAloneAndStillEndsTheRunWithAReply()
    {
        await using var harness = RunHarness.For(OverLimitBooking, OverLimitFlight);
        var runId = harness.Store.Start("My booking is BK-1002 and my flight was cancelled.");
        await harness.Store.WhenSettledAsync(runId);
        var approvalId = harness.Store.Get(runId)!.PendingApproval!.ApprovalId;

        var result = await harness.Store.AnswerAsync(approvalId, approved: false);
        await harness.Store.WhenSettledAsync(runId);

        Assert.Equal(AnswerResult.Accepted, result);
        var run = harness.Store.Get(runId)!;
        Assert.Equal(RunStates.Completed, run.State);
        Assert.Equal(ApprovalOutcomes.Rejected, run.Outcome);
        Assert.False(harness.Tools.WasInvoked("rebook"));
        Assert.Equal(FinalReply, run.Reply);
    }

    [Fact]
    public async Task ASecondAnswerToTheSameApprovalIsAConflict()
    {
        await using var harness = RunHarness.For(OverLimitBooking, OverLimitFlight);
        var runId = harness.Store.Start("My booking is BK-1002 and my flight was cancelled.");
        await harness.Store.WhenSettledAsync(runId);
        var approvalId = harness.Store.Get(runId)!.PendingApproval!.ApprovalId;

        var first = await harness.Store.AnswerAsync(approvalId, approved: true);
        await harness.Store.WhenSettledAsync(runId);
        var second = await harness.Store.AnswerAsync(approvalId, approved: false);

        Assert.Equal(AnswerResult.Accepted, first);
        Assert.Equal(AnswerResult.Conflict, second);
    }

    /// <summary>First answer wins, even when two land at the same moment.</summary>
    [Fact]
    public async Task TwoAnswersRacingOnTheSameApprovalProduceOneAcceptance()
    {
        await using var harness = RunHarness.For(OverLimitBooking, OverLimitFlight);
        var runId = harness.Store.Start("My booking is BK-1002 and my flight was cancelled.");
        await harness.Store.WhenSettledAsync(runId);
        var approvalId = harness.Store.Get(runId)!.PendingApproval!.ApprovalId;

        var results = await Task.WhenAll(
            Task.Run(() => harness.Store.AnswerAsync(approvalId, approved: true)),
            Task.Run(() => harness.Store.AnswerAsync(approvalId, approved: false)));

        Assert.Equal(1, results.Count(result => result == AnswerResult.Accepted));
        Assert.Equal(1, results.Count(result => result == AnswerResult.Conflict));
    }

    [Fact]
    public async Task AnUnknownApprovalIdIsNotFound()
    {
        await using var harness = RunHarness.For(UnderLimitBooking, UnderLimitFlight);

        Assert.Equal(AnswerResult.NotFound, await harness.Store.AnswerAsync("ap-nosuchthing", approved: true));
    }

    [Fact]
    public async Task AnApprovalNobodyAnswersExpiresAndEndsTheRun()
    {
        var options = Defaults with { ApprovalTimeoutSeconds = 60 };
        await using var harness = RunHarness.For(OverLimitBooking, OverLimitFlight, options);
        var runId = harness.Store.Start("My booking is BK-1002 and my flight was cancelled.");
        await harness.Store.WhenSettledAsync(runId);

        harness.Clock.Advance(TimeSpan.FromSeconds(61));
        await harness.Store.SweepAsync();
        await harness.Store.WhenSettledAsync(runId);

        var run = harness.Store.Get(runId)!;
        Assert.Equal(RunStates.Completed, run.State);
        Assert.Equal(ApprovalOutcomes.Expired, run.Outcome);
        Assert.Empty(harness.Store.ListPendingApprovals());
        Assert.False(harness.Tools.WasInvoked("rebook"));
    }

    [Fact]
    public async Task ASweepBeforeTheApprovalTimeoutLeavesThePendingRunAlone()
    {
        var options = Defaults with { ApprovalTimeoutSeconds = 60 };
        await using var harness = RunHarness.For(OverLimitBooking, OverLimitFlight, options);
        var runId = harness.Store.Start("My booking is BK-1002 and my flight was cancelled.");
        await harness.Store.WhenSettledAsync(runId);

        harness.Clock.Advance(TimeSpan.FromSeconds(30));
        await harness.Store.SweepAsync();

        Assert.Equal(RunStates.PendingApproval, harness.Store.Get(runId)!.State);
    }

    [Fact]
    public async Task ASettledRunIsEvictedOnceItsTtlHasPassed()
    {
        var options = Defaults with { RunTtlSeconds = 60 };
        await using var harness = RunHarness.For(UnderLimitBooking, UnderLimitFlight, options);
        var runId = harness.Store.Start("My booking is BK-1001 and my flight was cancelled.");
        await harness.Store.WhenSettledAsync(runId);
        Assert.NotNull(harness.Store.Get(runId));

        harness.Clock.Advance(TimeSpan.FromSeconds(61));
        await harness.Store.SweepAsync();

        Assert.Null(harness.Store.Get(runId));
    }

    [Fact]
    public async Task ARunThatOutlivesTheRunTimeoutFails()
    {
        var blocking = new BlockingChatClient();
        var options = Defaults with { RunTimeoutSeconds = 30 };
        await using var harness = RunHarness.For(UnderLimitBooking, UnderLimitFlight, options, blocking);

        try
        {
            var runId = harness.Store.Start("My booking is BK-1001 and my flight was cancelled.");
            Assert.Equal(RunStates.Running, harness.Store.Get(runId)!.State);

            harness.Clock.Advance(TimeSpan.FromSeconds(31));
            await harness.Store.SweepAsync();

            Assert.Equal(RunStates.Failed, harness.Store.Get(runId)!.State);
        }
        finally
        {
            blocking.Release();
        }
    }

    /// <summary>
    /// The shipped defaults put APPROVAL_TIMEOUT_SECONDS above RUN_TIMEOUT_SECONDS, so any
    /// approval that runs its full course outlives the run timeout on the wall clock. The
    /// run timeout measures the agent's own work, so the wait must not be charged to it;
    /// otherwise the default configuration fails the approvals this example demonstrates.
    /// </summary>
    [Fact]
    public async Task AnApprovalOutlastingTheRunTimeoutExpiresRatherThanFailingTheRun()
    {
        var options = Defaults with { ApprovalTimeoutSeconds = 600, RunTimeoutSeconds = 300 };

        // Held on its last turn, so the run is still running when the second sweep looks at
        // it. Without the hold the resume would finish first and the sweep would find a
        // settled run whatever the accounting said.
        var paused = new PausingChatClient(
            new ScriptedAgentChatClient(Script(OverLimitBooking, OverLimitFlight)), pauseOnTurn: 4);
        await using var harness = RunHarness.For(OverLimitBooking, OverLimitFlight, options, paused);

        var runId = harness.Store.Start("My booking is BK-1002 and my flight was cancelled.");

        try
        {
            await harness.Store.WhenSettledAsync(runId);
            Assert.Equal(RunStates.PendingApproval, harness.Store.Get(runId)!.State);

            harness.Clock.Advance(TimeSpan.FromSeconds(601));
            await harness.Store.SweepAsync();

            await paused.Reached.WaitAsync(TimeSpan.FromSeconds(10));
            await harness.Store.SweepAsync();

            Assert.Equal(RunStates.Running, harness.Store.Get(runId)!.State);
        }
        finally
        {
            paused.Release();
        }

        await harness.Store.WhenSettledAsync(runId);

        var run = harness.Store.Get(runId)!;
        Assert.Equal(RunStates.Completed, run.State);
        Assert.Equal(ApprovalOutcomes.Expired, run.Outcome);
        Assert.Null(run.Error);
    }

    /// <summary>
    /// AllowMultipleToolCalls is false on the rebooking agent, so a run has at most one
    /// approval outstanding. If that ever stops holding, the run says so rather than
    /// overwrite the first request with the second and answer whichever survived.
    /// </summary>
    [Fact]
    public async Task ASecondApprovalWhileOneIsOutstandingFailsTheRun()
    {
        // Neither call can be priced against BK-1002 under the limit, so whichever of them
        // the workflow raises first parks the run and the other one trips the guard.
        var client = new ScriptedAgentChatClient(
        [
            ScriptedAgentChatClient.ToolCall(
                AgentSetup.HandoffToolName, ("reasonForHandoff", "the traveller's flight was cancelled")),
            ScriptedAgentChatClient.ToolCalls(
                ScriptedAgentChatClient.ToolCall(
                    "rebook", ("booking_ref", OverLimitBooking), ("flight_id", OverLimitFlight)),
                ScriptedAgentChatClient.ToolCall(
                    "add_hotel", ("booking_ref", OverLimitBooking), ("hotel_id", "HTL-NOSUCHTHING"))),
            ScriptedAgentChatClient.Reply(FinalReply),
        ]);
        await using var harness = RunHarness.For(OverLimitBooking, OverLimitFlight, chatClient: client);

        var runId = harness.Store.Start("My booking is BK-1002 and my flight was cancelled.");
        await harness.Store.WhenSettledAsync(runId);

        var run = harness.Store.Get(runId)!;
        Assert.Equal(RunStates.Failed, run.State);
        Assert.Contains("second approval", run.Error);
        Assert.False(harness.Tools.WasInvoked("rebook"));
        Assert.False(harness.Tools.WasInvoked("add_hotel"));
    }

    /// <summary>
    /// Only one pass may read a run's stream. The pass raises the approval request from
    /// inside its own enumeration, so an answer arriving a moment later has to wait for that
    /// pass to leave before it sends the response and starts the resume. Held open here at
    /// the store's own log line, which is the last thing the pass does after publishing the
    /// request.
    /// </summary>
    [Fact]
    public async Task AnsweringWaitsForThePassThatRaisedTheRequest()
    {
        var logger = new PausingLogger<RunStore>(RunStore.PendingApprovalLogMessage);
        await using var harness = RunHarness.For(OverLimitBooking, OverLimitFlight, logger: logger);

        var runId = harness.Store.Start("My booking is BK-1002 and my flight was cancelled.");
        await logger.Reached.WaitAsync(TimeSpan.FromSeconds(10));

        var approvalId = harness.Store.Get(runId)!.PendingApproval!.ApprovalId;
        var answer = Task.Run(() => harness.Store.AnswerAsync(approvalId, approved: true));

        await Task.Delay(TimeSpan.FromMilliseconds(250));
        Assert.False(answer.IsCompleted);

        logger.Release();

        Assert.Equal(AnswerResult.Accepted, await answer.WaitAsync(TimeSpan.FromSeconds(10)));
        await harness.Store.WhenSettledAsync(runId);

        var run = harness.Store.Get(runId)!;
        Assert.Equal(RunStates.Completed, run.State);
        Assert.Equal(ApprovalOutcomes.Approved, run.Outcome);
        Assert.Equal(FinalReply, run.Reply);

        // Once, not twice: a second reader on the stream replays the approved call.
        Assert.Equal(
            1,
            harness.Tools.Invocations.Count(
                invocation => invocation.StartsWith("rebook", StringComparison.Ordinal)));
    }

    /// <summary>
    /// The same shape one step on: the answer has already claimed the request, so the guard
    /// on a second one cannot see a pending request to refuse. It goes by the generation
    /// instead, because a request raised by a retired pass is one no answer will ever be
    /// looked for and the run would sit on it for good.
    /// </summary>
    [Fact]
    public async Task AnApprovalRaisedByARetiredPassFailsTheRunRatherThanParkingIt()
    {
        var client = new ScriptedAgentChatClient(
        [
            ScriptedAgentChatClient.ToolCall(
                AgentSetup.HandoffToolName, ("reasonForHandoff", "the traveller's flight was cancelled")),
            ScriptedAgentChatClient.ToolCalls(
                ScriptedAgentChatClient.ToolCall(
                    "rebook", ("booking_ref", OverLimitBooking), ("flight_id", OverLimitFlight)),
                ScriptedAgentChatClient.ToolCall(
                    "add_hotel", ("booking_ref", OverLimitBooking), ("hotel_id", "HTL-NOSUCHTHING"))),
            ScriptedAgentChatClient.Reply(FinalReply),
        ]);
        var logger = new PausingLogger<RunStore>(RunStore.PendingApprovalLogMessage);
        await using var harness = RunHarness.For(
            OverLimitBooking, OverLimitFlight, chatClient: client, logger: logger);

        var runId = harness.Store.Start("My booking is BK-1002 and my flight was cancelled.");
        await logger.Reached.WaitAsync(TimeSpan.FromSeconds(10));

        var approvalId = harness.Store.Get(runId)!.PendingApproval!.ApprovalId;
        var answer = Task.Run(() => harness.Store.AnswerAsync(approvalId, approved: true));

        // The claim happens first thing inside the answer, so the pass is released into a
        // run whose pending request has gone and whose generation has moved on.
        await WaitUntilAsync(() => harness.Store.ListPendingApprovals().Count == 0);
        logger.Release();

        Assert.Equal(AnswerResult.Accepted, await answer.WaitAsync(TimeSpan.FromSeconds(10)));
        await harness.Store.WhenSettledAsync(runId);

        var run = harness.Store.Get(runId)!;
        Assert.Equal(RunStates.Failed, run.State);
        Assert.Contains("second approval", run.Error);
        Assert.Null(run.PendingApproval);
        Assert.Empty(harness.Store.ListPendingApprovals());
    }

    /// <summary>
    /// The bound is five real seconds in production, too long for a test to wait on. Shrunk
    /// here to a few milliseconds and never released, so the wait in <c>DecideAsync</c>
    /// times out deterministically and fast, exactly as a genuinely stuck pass would.
    /// </summary>
    [Fact]
    public async Task AHandoverPastTheBoundFailsTheRunRatherThanStartingASecondReader()
    {
        var logger = new PausingLogger<RunStore>(RunStore.PendingApprovalLogMessage);
        await using var harness = RunHarness.For(
            OverLimitBooking, OverLimitFlight, logger: logger, passHandover: TimeSpan.FromMilliseconds(50));

        var runId = harness.Store.Start("My booking is BK-1002 and my flight was cancelled.");
        await logger.Reached.WaitAsync(TimeSpan.FromSeconds(10));

        var approvalId = harness.Store.Get(runId)!.PendingApproval!.ApprovalId;
        var result = await harness.Store.AnswerAsync(approvalId, approved: true).WaitAsync(TimeSpan.FromSeconds(10));

        Assert.Equal(AnswerResult.Accepted, result);

        var run = harness.Store.Get(runId)!;
        Assert.Equal(RunStates.Failed, run.State);
        Assert.Contains("did not release its stream", run.Error);
        Assert.Null(run.PendingApproval);

        // The human's answer is still recorded on the entry, even though the run behind it
        // failed: nothing is left showing "pending" for a request that was, in fact, answered.
        var entry = Assert.Single(run.Approvals, approval => approval.ApprovalId == approvalId);
        Assert.Equal(ApprovalOutcomes.Approved, entry.Outcome);
        Assert.NotNull(entry.DecidedAt);

        logger.Release();
        await harness.Store.WhenSettledAsync(runId);
    }

    /// <summary>
    /// A decision can reach the lock in <c>DecideAsync</c> after the run has already settled
    /// by some other path -- here, the run timeout, racing the same claimed answer. Before the
    /// fix this branch returned without writing the entry, so GET /runs/{id} went on showing
    /// "pending" for a request somebody had, in fact, answered. Both this branch and the one
    /// below it call the same <c>RecordApprovalEntryOutcomeLocked</c>, so this also stands for
    /// the sibling fix at the "run was disposed" branch, which a public API cannot observe
    /// once it has actually happened: <see cref="RunStore.DisposeAsync"/> removes a run from
    /// every query before it disposes it, by design.
    /// </summary>
    [Fact]
    public async Task ADecisionThatArrivesAfterTheRunTimeoutSettledItStillRecordsTheEntryOutcome()
    {
        var logger = new PausingLogger<RunStore>(RunStore.PendingApprovalLogMessage);
        var options = Defaults with { RunTimeoutSeconds = 30 };
        await using var harness = RunHarness.For(OverLimitBooking, OverLimitFlight, options, logger: logger);

        var runId = harness.Store.Start("My booking is BK-1002 and my flight was cancelled.");
        await logger.Reached.WaitAsync(TimeSpan.FromSeconds(10));
        var approvalId = harness.Store.Get(runId)!.PendingApproval!.ApprovalId;

        // Claims the pending request (moving the run back to "running") and then blocks on
        // the still-paused pass, exactly where AnsweringWaitsForThePassThatRaisedTheRequest
        // holds it.
        var answer = Task.Run(() => harness.Store.AnswerAsync(approvalId, approved: true));
        await WaitUntilAsync(() => harness.Store.ListPendingApprovals().Count == 0);

        // The claim banks the wait so far against PendingElapsed, so advancing the clock here
        // charges the run timeout rather than the approval timeout: exactly the accounting
        // WorkAfterAnApprovalStaysInTheTravellersTrace's neighbours rely on elsewhere in this
        // file. The sweep does not touch the paused pass, so this is not a race.
        harness.Clock.Advance(TimeSpan.FromSeconds(31));
        await harness.Store.SweepAsync();
        Assert.Equal(RunStates.Failed, harness.Store.Get(runId)!.State);

        logger.Release();

        Assert.Equal(AnswerResult.Accepted, await answer.WaitAsync(TimeSpan.FromSeconds(10)));

        var run = harness.Store.Get(runId)!;
        Assert.Equal(RunStates.Failed, run.State);
        Assert.Equal("the run exceeded RUN_TIMEOUT_SECONDS", run.Error);

        var entry = Assert.Single(run.Approvals, approval => approval.ApprovalId == approvalId);
        Assert.NotEqual(ApprovalOutcomes.Pending, entry.Outcome);
        Assert.Equal(ApprovalOutcomes.Approved, entry.Outcome);
        Assert.NotNull(entry.DecidedAt);
    }

    /// <summary>
    /// The approval arrives on a different HTTP request from the one that started the run,
    /// so the run captures its root activity context and restores it around every later
    /// pass. Without that the spans produced after an approval join the approval request's
    /// trace and the design's one trace per traveller message does not hold.
    /// </summary>
    [Fact]
    public async Task WorkAfterAnApprovalStaysInTheTravellersTrace()
    {
        var spans = new List<Activity>();
        var spanLock = new Lock();

        using var listener = new ActivityListener
        {
            ShouldListenTo = source => source.Name == Sources.AgentRebooking || source.Name == TestSourceName,
            Sample = (ref ActivityCreationOptions<ActivityContext> _) => ActivitySamplingResult.AllDataAndRecorded,
            ActivityStopped = activity =>
            {
                lock (spanLock)
                {
                    spans.Add(activity);
                }
            },
        };
        ActivitySource.AddActivityListener(listener);

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

        ActivityContext approvalRequest;
        using (var request = TestSource.StartActivity("POST /approvals/{id}", ActivityKind.Server)!)
        {
            approvalRequest = request.Context;
            await harness.Store.AnswerAsync(approvalId, approved: true);
        }

        await harness.Store.WhenSettledAsync(runId);

        List<Activity> mine;
        lock (spanLock)
        {
            mine = [.. spans.Where(span => (string?)span.GetTagItem("base14.run.id") == runId)];
        }

        Assert.NotEqual(travellerRequest.TraceId, approvalRequest.TraceId);

        var runSpan = Assert.Single(mine, span => span.OperationName == "base14.agent.run");
        Assert.Equal(travellerRequest.TraceId, runSpan.TraceId);
        Assert.Equal(travellerRequest.SpanId, runSpan.ParentSpanId);

        var resumeSpan = Assert.Single(mine, span => span.OperationName == "base14.agent.resume");
        Assert.Equal(travellerRequest.TraceId, resumeSpan.TraceId);
        Assert.Equal(travellerRequest.SpanId, resumeSpan.ParentSpanId);
    }

    private static async Task WaitUntilAsync(Func<bool> condition)
    {
        var deadline = DateTime.UtcNow.AddSeconds(10);
        while (!condition())
        {
            Assert.True(DateTime.UtcNow < deadline, "the condition never held");
            await Task.Delay(TimeSpan.FromMilliseconds(5));
        }
    }
}
