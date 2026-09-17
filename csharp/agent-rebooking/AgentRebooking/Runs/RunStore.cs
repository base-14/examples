using System.Diagnostics;
using System.Text.Json;
using AgentRebooking.Telemetry;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

namespace AgentRebooking.Runs;

/// <summary>
/// Holds every in-flight and recently finished run in memory, drives the handoff workflow, and
/// answers or parks the approval requests it raises. A restart drops everything.
/// </summary>
public sealed class RunStore(
    Func<Workflow> workflowFactory,
    ApprovalGate gate,
    RunStoreOptions options,
    ApprovalTelemetry telemetry,
    TimeProvider timeProvider,
    ILogger<RunStore> logger) : IAsyncDisposable
{
    // A run needs two passes: one up to the approval, one after it. The cap stops a workflow
    // that never settles from spinning.
    private const int MaxStreamPasses = 24;

    // Between passes, so a workflow that never settles cannot burn a core.
    private static readonly TimeSpan BetweenPasses = TimeSpan.FromMilliseconds(50);

    // How long a caller taking the stream over waits for the pass holding it. Running past it
    // fails the run: a second reader on one stream is the thing being prevented. Internal so a
    // test can shrink it.
    internal TimeSpan PassHandover { get; init; } = TimeSpan.FromSeconds(5);

    /// <summary>
    /// The last thing the pass that parks a run does before leaving the stream. RunStoreTests
    /// freezes a pass on this exact string, so reword it there too.
    /// </summary>
    internal const string PendingApprovalLogMessage = "Run {RunId} is waiting on approval {ApprovalId} for {Tool}: {Reason}";

    private readonly Lock _sync = new();
    private readonly Dictionary<string, RunRecord> _runs = [];

    /// <summary>
    /// Starts a run and returns at once with its id. The workflow runs on a background task: a
    /// message takes tens of seconds locally, and the approval arrives on another request.
    /// </summary>
    public string Start(string message)
    {
        var record = new RunRecord
        {
            Id = "run-" + Guid.NewGuid().ToString("N")[..12],
            Message = message,
            // Restored around every later pass, or the post-approval spans would join the
            // approver's trace instead of the traveller's.
            RootContext = Activity.Current?.Context ?? default,
            StartedAt = timeProvider.GetUtcNow(),
        };

        lock (_sync)
        {
            _runs[record.Id] = record;
            record.Pump = Task.Run(() => PumpAsync(record));
        }

        return record.Id;
    }

    public RunSnapshot? Get(string runId)
    {
        lock (_sync)
        {
            return _runs.TryGetValue(runId, out var record) ? Snapshot(record) : null;
        }
    }

    public IReadOnlyList<ApprovalEntry> ListPendingApprovals()
    {
        lock (_sync)
        {
            return
            [
                .. _runs.Values
                    .Where(record => record.State == RunStates.PendingApproval)
                    .SelectMany(record => record.Approvals)
                    .Where(approval => approval.Outcome == ApprovalOutcomes.Pending)
                    .OrderBy(approval => approval.RequestedAt)
            ];
        }
    }

    /// <summary>The run an approval belongs to, pending or already decided.</summary>
    public string? FindRunIdForApproval(string approvalId)
    {
        lock (_sync)
        {
            return _runs.Values
                .FirstOrDefault(record => record.Approvals.Any(approval => approval.ApprovalId == approvalId))?.Id;
        }
    }

    /// <summary>
    /// Answers one pending approval. The first answer wins: a second answer, or an answer
    /// for a run that has already finished, comes back as <see cref="AnswerResult.Conflict"/>.
    /// </summary>
    public async Task<AnswerResult> AnswerAsync(string approvalId, bool approved)
    {
        if (!TryClaim(approvalId, out var record, out var pending, out var waited))
        {
            lock (_sync)
            {
                var known = _runs.Values.Any(
                    candidate => candidate.Approvals.Any(approval => approval.ApprovalId == approvalId));
                return known ? AnswerResult.Conflict : AnswerResult.NotFound;
            }
        }

        await DecideAsync(
            record, pending, approved,
            approved ? ApprovalOutcomes.Approved : ApprovalOutcomes.Rejected,
            waited);

        return AnswerResult.Accepted;
    }

    /// <summary>
    /// Takes the pending request off the run under one lock, so two racing answers cannot both
    /// reach the workflow. The loser finds nothing to claim.
    /// </summary>
    private bool TryClaim(
        string approvalId, out RunRecord record, out PendingRequest pending, out TimeSpan waited)
    {
        lock (_sync)
        {
            var match = _runs.Values.FirstOrDefault(candidate => candidate.Pending?.ApprovalId == approvalId);
            if (match?.Pending is not { } claimed)
            {
                record = null!;
                pending = null!;
                waited = TimeSpan.Zero;
                return false;
            }

            waited = ClaimPending(match, timeProvider.GetUtcNow());
            record = match;
            pending = claimed;
            return true;
        }
    }

    /// <summary>
    /// Takes a pending request off a run and puts it back in <c>running</c>, for an answer
    /// and for an expiry alike. Called under the <c>_sync</c> lock.
    /// </summary>
    /// <remarks>
    /// Two things the rest of the file depends on. The waiting time is banked, so the 300 second
    /// run timeout never charges a run for the human's thinking against a 600 second approval
    /// timeout. And the generation moves on, retiring the pass that raised the request so it
    /// cannot read the stream alongside the resume. The pending clock stops at the claim: from
    /// there on the time is the agent's own again.
    /// </remarks>
    /// <returns>How long the run waited on the human, which is the histogram's measurement.</returns>
    private static TimeSpan ClaimPending(RunRecord record, DateTimeOffset now)
    {
        record.Pending = null;
        record.State = RunStates.Running;
        record.Generation++;

        if (record.PendingSince is not { } since)
        {
            return TimeSpan.Zero;
        }

        var waited = now - since;
        record.PendingElapsed += waited;
        record.PendingSince = null;
        return waited;
    }

    /// <summary>
    /// Expires stale approvals, fails runs past the run timeout and evicts settled runs past the
    /// TTL. Driven by <see cref="RunSweeper"/>, and by tests, so the clock is a
    /// <see cref="TimeProvider"/> rather than a timer.
    /// </summary>
    public async Task SweepAsync()
    {
        var now = timeProvider.GetUtcNow();
        List<(RunRecord Record, PendingRequest Pending, TimeSpan Waited)> expired = [];
        List<RunRecord> timedOut = [];
        List<RunRecord> evicted = [];

        lock (_sync)
        {
            foreach (var record in _runs.Values.ToList())
            {
                if (record.State == RunStates.PendingApproval && record.Pending is { } pending)
                {
                    var requestedAt = record.Approvals
                        .First(approval => approval.ApprovalId == pending.ApprovalId).RequestedAt;
                    if (now - requestedAt >= TimeSpan.FromSeconds(options.ApprovalTimeoutSeconds))
                    {
                        // Under the same lock an answer claims in, so an approval landing mid
                        // sweep is not answered twice.
                        expired.Add((record, pending, ClaimPending(record, now)));
                    }
                }
                else if (record.State == RunStates.Running
                    && now - record.StartedAt - record.PendingElapsed
                        >= TimeSpan.FromSeconds(options.RunTimeoutSeconds))
                {
                    timedOut.Add(record);
                }
                else if (IsSettled(record.State)
                    && record.SettledAt is { } settledAt
                    && now - settledAt >= TimeSpan.FromSeconds(options.RunTtlSeconds))
                {
                    _runs.Remove(record.Id);
                    evicted.Add(record);
                }
            }
        }

        // Together, not in turn: one run slow to hand over its stream must not hold up the tick.
        await Task.WhenAll(expired.Select(async item =>
        {
            logger.LogInformation(
                "Approval {ApprovalId} on run {RunId} expired", item.Pending.ApprovalId, item.Record.Id);
            await DecideAsync(item.Record, item.Pending, approved: false, ApprovalOutcomes.Expired, item.Waited);
        }));

        foreach (var record in timedOut)
        {
            // Before the cancellation, not after: the pass also fails the run on cancellation
            // and the first failure wins, so the other order makes the message a race.
            Fail(record, "the run exceeded RUN_TIMEOUT_SECONDS");
            await record.Cancellation.CancelAsync();
        }

        foreach (var record in evicted)
        {
            await DisposeRecordAsync(record);
        }
    }

    /// <summary>
    /// Completes when the run's current pass has settled: pending an approval, completed or
    /// failed. Answering an approval starts a new pass, so callers await this again after
    /// <see cref="AnswerAsync"/>.
    /// </summary>
    public Task WhenSettledAsync(string runId)
    {
        lock (_sync)
        {
            return _runs.TryGetValue(runId, out var record) ? record.Pump : Task.CompletedTask;
        }
    }

    public async ValueTask DisposeAsync()
    {
        List<RunRecord> records;
        lock (_sync)
        {
            records = [.. _runs.Values];
            _runs.Clear();
        }

        foreach (var record in records)
        {
            await DisposeRecordAsync(record);
        }
    }

    private static bool IsSettled(string state) => state is RunStates.Completed or RunStates.Failed;

    private static RunSnapshot Snapshot(RunRecord record) => new(
        record.Id, record.State, record.Outcome, record.Reply, record.Error,
        [.. record.ToolCalls], [.. record.Approvals]);

    private static string SerialiseArguments(IDictionary<string, object?>? arguments) =>
        JsonSerializer.Serialize(arguments ?? new Dictionary<string, object?>());

    private async Task PumpAsync(RunRecord record)
    {
        using var activity = StartRunActivity(record, "base14.agent.run");

        try
        {
            var messages = new List<ChatMessage> { new(ChatRole.User, record.Message) };
            var run = await InProcessExecution.RunStreamingAsync(
                workflowFactory(), messages, cancellationToken: record.Cancellation.Token);

            lock (_sync)
            {
                record.Run = run;
            }

            // RunStreamingAsync leaves the run NotStarted and yields nothing until a turn
            // token arrives. Undocumented at 1.21.0.
            await run.TrySendMessageAsync(new TurnToken(emitEvents: true));

            await DrainAsync(record, record.Cancellation.Token);
        }
        catch (OperationCanceledException)
        {
            Fail(record, "the run was cancelled");
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "Run {RunId} failed", record.Id);
            activity?.AddException(ex);
            Fail(record, ex.Message);
        }
        finally
        {
            ReleaseRunActivity(record, activity);
        }
    }

    private async Task ResumeAsync(RunRecord record)
    {
        using var activity = StartRunActivity(record, "base14.agent.resume");

        try
        {
            await DrainAsync(record, record.Cancellation.Token);
        }
        catch (OperationCanceledException)
        {
            Fail(record, "the run was cancelled");
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "Run {RunId} failed after an approval", record.Id);
            activity?.AddException(ex);
            Fail(record, ex.Message);
        }
        finally
        {
            ReleaseRunActivity(record, activity);
        }
    }

    // A background task inherits whichever activity was current on the request that started it.
    // Clearing that and parenting to the captured context keeps every span in the traveller's
    // trace. The activity is published on the record so Fail can reach it; see the rule there.
    private Activity? StartRunActivity(RunRecord record, string name)
    {
        Activity.Current = null;
        var activity = Sources.Activity.StartActivity(name, ActivityKind.Internal, record.RootContext);
        activity?.SetTag(ApprovalTelemetry.RunIdAttribute, record.Id);

        lock (_sync)
        {
            record.PassActivity = activity;
        }

        return activity;
    }

    // Unpublished before the using block stops it, so a later failure finds no span rather than
    // writing onto an exported one. Compared by reference: a resume that already published its
    // own activity owns the field.
    private void ReleaseRunActivity(RunRecord record, Activity? activity)
    {
        lock (_sync)
        {
            if (ReferenceEquals(record.PassActivity, activity))
            {
                record.PassActivity = null;
            }
        }
    }

    private async Task DrainAsync(RunRecord record, CancellationToken cancellationToken)
    {
        StreamingRun run;
        int generation;
        lock (_sync)
        {
            run = record.Run ?? throw new InvalidOperationException($"Run '{record.Id}' has no workflow run.");
            generation = record.Generation;
        }

        for (var pass = 0; pass < MaxStreamPasses; pass++)
        {
            var sawEvent = false;

            await foreach (var evt in run.WatchStreamAsync(
                blockOnPendingRequest: false, cancellationToken: cancellationToken))
            {
                sawEvent = true;

                switch (evt)
                {
                    case RequestInfoEvent request:
                        await HandleApprovalRequestAsync(record, request, run, generation, cancellationToken);
                        break;
                    case AgentResponseEvent response:
                        RecordResponse(record, response);
                        break;
                    case ExecutorFailedEvent failed:
                        Fail(record, $"executor '{failed.ExecutorId}' failed: {failed.Data}");
                        return;
                    case WorkflowErrorEvent error:
                        Fail(record, $"the workflow reported an error: {error.Data}");
                        return;
                }
            }

            lock (_sync)
            {
                // A stale generation means a resume owns the stream now. Leave it alone.
                if (record.Generation != generation
                    || record.State is RunStates.PendingApproval
                    || IsSettled(record.State))
                {
                    return;
                }
            }

            // A finished handoff workflow settles on Idle, not Ended.
            var status = await run.GetStatusAsync(cancellationToken);
            if (status is RunStatus.Idle or RunStatus.Ended)
            {
                Complete(record);
                return;
            }

            if (!sawEvent)
            {
                Fail(record, $"the workflow stopped producing events while {status}");
                return;
            }

            // Real time, not the injected clock: this is about not burning a core.
            await Task.Delay(BetweenPasses, cancellationToken);
        }

        Fail(record, $"the workflow did not settle within {MaxStreamPasses} passes over its stream");
    }

    private async Task HandleApprovalRequestAsync(
        RunRecord record,
        RequestInfoEvent evt,
        StreamingRun run,
        int generation,
        CancellationToken cancellationToken)
    {
        lock (_sync)
        {
            // AllowMultipleToolCalls is false, so a run has at most one approval outstanding; a
            // second means that no longer holds and answering either would be guesswork. A stale
            // generation means this pass is retired, and publishing would park the run for good.
            if (record.Pending is not null || record.Generation != generation)
            {
                Fail(record, "the workflow raised a second approval while one was outstanding");
                return;
            }
        }

        if (!evt.Request.TryGetDataAs<ToolApprovalRequestContent>(out var content) || content is null)
        {
            Fail(record, $"an external request of type {evt.Request.PortInfo.RequestType} is not a tool approval");
            return;
        }

        // Declared as ToolCallContent, which carries only a call id. At runtime it is a
        // FunctionCallContent, which is where the name and arguments are.
        if (content.ToolCall is not FunctionCallContent call)
        {
            Fail(record, "a tool approval request carried no function call");
            return;
        }

        var decision = await gate.DecideAsync(call, cancellationToken);
        var now = timeProvider.GetUtcNow();
        var approvalId = "ap-" + Guid.NewGuid().ToString("N")[..10];

        var entry = new ApprovalEntry(
            ApprovalId: approvalId,
            RunId: record.Id,
            Tool: call.Name,
            BookingRef: decision.BookingRef,
            OfferId: decision.OfferId,
            Amount: decision.Amount,
            Limit: decision.Limit,
            Reason: decision.Reason,
            Outcome: decision.AutoApprove ? ApprovalOutcomes.Auto : ApprovalOutcomes.Pending,
            RequestedAt: now,
            DecidedAt: decision.AutoApprove ? now : null);

        if (decision.AutoApprove)
        {
            lock (_sync)
            {
                record.Approvals.Add(entry);
                record.Outcome = ApprovalOutcomes.Auto;
            }

            telemetry.AutoApproved(entry);
            await run.SendResponseAsync(evt.Request.CreateResponse(content.CreateResponse(approved: true)));
            return;
        }

        // Opened and closed inside the pass, so it lands in the traveller's trace. Its context
        // rides on the pending request for the decided span to link back to.
        var requested = telemetry.Requested(entry);

        lock (_sync)
        {
            record.Approvals.Add(entry);
            record.Pending = new PendingRequest(approvalId, evt.Request, content, requested);
            record.State = RunStates.PendingApproval;
            record.PendingSince = now;
        }

        logger.LogInformation(PendingApprovalLogMessage, record.Id, approvalId, call.Name, decision.Reason);
    }

    /// <summary>
    /// Sends one already-claimed decision into the workflow and starts the pass that runs the
    /// rest of the turn. An expiry is a rejection the workflow cannot tell apart.
    /// </summary>
    private async Task DecideAsync(
        RunRecord record, PendingRequest pending, bool approved, string outcome, TimeSpan waited)
    {
        // Above everything that can go wrong, because both ways out pass through here. The
        // handover can fail and take the run with it; the human's answer was still made.
        Decided(record, pending, outcome, waited);

        // The pass that raised the request can still be unwinding. Only one pass may read a
        // StreamingRun, so the resume waits for it; claiming the request already retired it, so
        // it leaves at its next checkpoint. A pass that overruns the bound ends the run.
        if (!await TryAwaitPassAsync(record))
        {
            // The workflow never hears it, but the answer was made: record it so GET /runs/{id}
            // stops showing "pending". The run's own state carries the failure.
            RecordApprovalEntryOutcome(record, pending, outcome);
            Fail(
                record,
                $"the workflow did not release its stream within {PassHandover.TotalSeconds:0}s of the decision");
            return;
        }

        StreamingRun run;

        lock (_sync)
        {
            if (IsSettled(record.State))
            {
                // As above. Not record.Outcome: that stays whatever the settling path wrote,
                // because the workflow was never told.
                RecordApprovalEntryOutcomeLocked(record, pending, outcome);
                return;
            }

            // After the wait: a shutdown racing this answer takes the run once its pass unwinds.
            if (record.Run is not { } current)
            {
                // As above: the answer happened, so the entry says so.
                RecordApprovalEntryOutcomeLocked(record, pending, outcome);
                Fail(record, "the run was disposed while its approval was being answered");
                return;
            }

            run = current;

            // Below the wait too, so GET /runs/{id} cannot show a decided outcome before the
            // workflow has been told.
            record.Outcome = outcome;
            RecordApprovalEntryOutcomeLocked(record, pending, outcome);
        }

        try
        {
            await run.SendResponseAsync(pending.Request.CreateResponse(pending.Content.CreateResponse(approved)));
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "Run {RunId} could not accept the approval response", record.Id);
            Fail(record, ex.Message);
            return;
        }

        lock (_sync)
        {
            record.Pump = Task.Run(() => ResumeAsync(record), CancellationToken.None);
        }
    }

    private void Decided(RunRecord record, PendingRequest pending, string outcome, TimeSpan waited)
    {
        ApprovalEntry? entry;
        lock (_sync)
        {
            entry = record.Approvals.FirstOrDefault(
                approval => approval.ApprovalId == pending.ApprovalId);
        }

        if (entry is not null)
        {
            telemetry.Decided(entry, pending.RequestedContext, outcome, waited);
        }
    }

    private void RecordApprovalEntryOutcome(RunRecord record, PendingRequest pending, string outcome)
    {
        lock (_sync)
        {
            RecordApprovalEntryOutcomeLocked(record, pending, outcome);
        }
    }

    /// <summary>Called under <c>_sync</c>, which every caller already holds.</summary>
    private void RecordApprovalEntryOutcomeLocked(RunRecord record, PendingRequest pending, string outcome)
    {
        var index = record.Approvals.FindIndex(approval => approval.ApprovalId == pending.ApprovalId);
        if (index >= 0)
        {
            record.Approvals[index] = record.Approvals[index] with
            {
                Outcome = outcome,
                DecidedAt = timeProvider.GetUtcNow(),
            };
        }
    }

    /// <summary>
    /// Waits, bounded, for the run's current pass to finish. False means the stream still has a
    /// reader and the caller must not become a second one.
    /// </summary>
    private async Task<bool> TryAwaitPassAsync(RunRecord record)
    {
        Task pass;
        lock (_sync)
        {
            pass = record.Pump;
        }

        try
        {
            await pass.WaitAsync(PassHandover);
            return true;
        }
        catch (TimeoutException)
        {
            logger.LogWarning(
                "Run {RunId} did not finish its pass over the stream within {Seconds}s",
                record.Id, PassHandover.TotalSeconds);
            return false;
        }
        catch (Exception ex)
        {
            // The pass threw, so it is over and the stream is free.
            logger.LogWarning(ex, "Run {RunId} ended its pass over the stream with an error", record.Id);
            return true;
        }
    }

    private void RecordResponse(RunRecord record, AgentResponseEvent evt)
    {
        if (evt.Response is not { } response)
        {
            return;
        }

        var now = timeProvider.GetUtcNow();

        lock (_sync)
        {
            foreach (var call in response.Messages.SelectMany(message => message.Contents).OfType<FunctionCallContent>())
            {
                // Each pass replays part of the agent's messages, so a call can arrive twice.
                if (record.SeenCallIds.Add(call.CallId))
                {
                    record.ToolCalls.Add(new ToolCallEntry(call.Name, SerialiseArguments(call.Arguments), now));
                }
            }

            if (!string.IsNullOrWhiteSpace(response.Text))
            {
                record.Reply = response.Text;
            }
        }
    }

    private void Complete(RunRecord record)
    {
        lock (_sync)
        {
            if (IsSettled(record.State))
            {
                return;
            }

            record.State = RunStates.Completed;
            record.SettledAt = timeProvider.GetUtcNow();
        }
    }

    /// <summary>
    /// Settles a run as failed and marks the span that owns the failure.
    /// </summary>
    /// <remarks>
    /// The rule, applied at every call site: a failure belongs to the span of the pass that was
    /// running when it was recorded, published in <see cref="RunRecord.PassActivity"/>. Never
    /// <see cref="Activity.Current"/>, which is nothing on the sweeper's thread and the
    /// approver's own server span on <c>POST /approvals/{id}</c>. A run parked on an approval
    /// has no live pass, so a failure there marks no span and the error log is all a reader
    /// gets; the alternatives are writing onto an exported span or a meaningless zero-length one.
    /// </remarks>
    private void Fail(RunRecord record, string error)
    {
        lock (_sync)
        {
            if (IsSettled(record.State))
            {
                return;
            }

            record.State = RunStates.Failed;
            record.Error = error;
            record.Pending = null;
            record.SettledAt = timeProvider.GetUtcNow();

            record.PassActivity?.SetStatus(ActivityStatusCode.Error, error);
        }

        // The one log line every failed run has, whatever reached here.
        logger.LogError("Run {RunId} failed: {Error}", record.Id, error);
    }

    private async Task DisposeRecordAsync(RunRecord record)
    {
        // Cancel, wait for the pass to unwind, then take the run and the token source away. A
        // pass still inside the stream would otherwise find them gone.
        await record.Cancellation.CancelAsync();

        if (!await TryAwaitPassAsync(record))
        {
            // Still reading. Leaking costs a process that is on its way out; pulling them from
            // under a live pass costs more.
            logger.LogWarning("Run {RunId} was left undisposed because its pass is still on the stream", record.Id);
            return;
        }

        StreamingRun? run;
        lock (_sync)
        {
            run = record.Run;
            record.Run = null;
        }

        if (run is not null)
        {
            try
            {
                await run.DisposeAsync();
            }
            catch (Exception ex)
            {
                logger.LogWarning(ex, "Disposing run {RunId} failed", record.Id);
            }
        }

        record.Cancellation.Dispose();
    }

    private sealed record PendingRequest(
        string ApprovalId,
        ExternalRequest Request,
        ToolApprovalRequestContent Content,
        ActivityContext RequestedContext);

    private sealed class RunRecord
    {
        public required string Id { get; init; }

        public required string Message { get; init; }

        public ActivityContext RootContext { get; init; }

        public DateTimeOffset StartedAt { get; init; }

        /// <summary>When the run entered <c>pending_approval</c>, null while it is running.</summary>
        public DateTimeOffset? PendingSince { get; set; }

        /// <summary>Total time this run has spent waiting on a human, excluded from the run timeout.</summary>
        public TimeSpan PendingElapsed { get; set; }

        /// <summary>Bumped whenever a pending request is claimed, to retire the pass that raised it.</summary>
        public int Generation { get; set; }

        public string State { get; set; } = RunStates.Running;

        public string? Outcome { get; set; }

        public string? Reply { get; set; }

        public string? Error { get; set; }

        public DateTimeOffset? SettledAt { get; set; }

        public List<ToolCallEntry> ToolCalls { get; } = [];

        public List<ApprovalEntry> Approvals { get; } = [];

        public HashSet<string> SeenCallIds { get; } = [];

        /// <summary>
        /// The span of the pass currently reading this run's stream, null between passes. Read
        /// and written under <c>_sync</c>, so <see cref="RunStore.Fail"/> can mark the run's own
        /// span from a thread whose ambient activity belongs to somebody else.
        /// </summary>
        public Activity? PassActivity { get; set; }

        public StreamingRun? Run { get; set; }

        public PendingRequest? Pending { get; set; }

        public Task Pump { get; set; } = Task.CompletedTask;

        public CancellationTokenSource Cancellation { get; } = new();
    }
}

/// <summary>
/// Runs <see cref="RunStore.SweepAsync"/> on a fixed interval so approvals expire, stuck
/// runs fail and settled runs are evicted without an HTTP request to trigger it.
/// </summary>
public sealed class RunSweeper(RunStore store, ILogger<RunSweeper> logger) : BackgroundService
{
    private static readonly TimeSpan Interval = TimeSpan.FromSeconds(5);

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        using var timer = new PeriodicTimer(Interval);

        while (await timer.WaitForNextTickAsync(stoppingToken))
        {
            try
            {
                await store.SweepAsync();
            }
            catch (OperationCanceledException)
            {
                return;
            }
            catch (Exception ex)
            {
                logger.LogError(ex, "The run sweep failed");
            }
        }
    }
}
