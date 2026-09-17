using System.Diagnostics.Metrics;
using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using AgentRebooking.Agents;
using AgentRebooking.Api;
using AgentRebooking.Runs;
using AgentRebooking.Telemetry;
using AgentRebooking.Tests.Support;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace AgentRebooking.Tests;

/// <summary>
/// The four run endpoints over the ASP.NET test host, with the same scripted chat client
/// and local tools the run store tests use. <c>GET /health</c> is mapped by Program.cs and
/// is not touched by this task.
/// </summary>
public class EndpointTests
{
    private const string UnderLimitBooking = "BK-1001";
    private const string UnderLimitFlight = "FL-201";
    private const string OverLimitBooking = "BK-1002";
    private const string OverLimitFlight = "FL-301";

    private static readonly JsonSerializerOptions Json = JsonSerializerOptions.Web;

    [Fact]
    public async Task PostRunsAcceptsTheMessageAndReturnsTheRunId()
    {
        await using var harness = await Harness.StartAsync(UnderLimitBooking, UnderLimitFlight);

        var response = await harness.Client.PostAsJsonAsync("/runs", new { message = "My flight was cancelled." });

        Assert.Equal(HttpStatusCode.Accepted, response.StatusCode);
        var started = await response.Content.ReadFromJsonAsync<StartRunResponse>(Json);
        Assert.NotNull(started);
        Assert.StartsWith("run-", started.RunId, StringComparison.Ordinal);
        Assert.Equal(RunStates.Running, started.State);
        Assert.Equal($"/runs/{started.RunId}", response.Headers.Location?.ToString());
    }

    [Fact]
    public async Task PostRunsWithoutAMessageIsRejected()
    {
        await using var harness = await Harness.StartAsync(UnderLimitBooking, UnderLimitFlight);

        var response = await harness.Client.PostAsJsonAsync("/runs", new { message = "   " });

        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
    }

    [Fact]
    public async Task GetRunReturnsTheCompletedRunWithItsToolLog()
    {
        await using var harness = await Harness.StartAsync(UnderLimitBooking, UnderLimitFlight);
        var runId = await harness.StartRunAsync("My booking is BK-1001 and my flight was cancelled.");

        var run = await harness.Client.GetFromJsonAsync<RunSnapshot>($"/runs/{runId}", Json);

        Assert.NotNull(run);
        Assert.Equal(RunStates.Completed, run.State);
        Assert.Contains(run.ToolCalls, call => call.Tool == "rebook");
        Assert.Null(run.PendingApproval);
    }

    [Fact]
    public async Task GetRunForAnUnknownIdIsNotFound()
    {
        await using var harness = await Harness.StartAsync(UnderLimitBooking, UnderLimitFlight);

        var response = await harness.Client.GetAsync("/runs/run-nosuchthing");

        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
    }

    [Fact]
    public async Task GetApprovalsListsThePendingApprovalWithItsAmountAndLimit()
    {
        await using var harness = await Harness.StartAsync(OverLimitBooking, OverLimitFlight);
        await harness.StartRunAsync("My booking is BK-1002 and my flight was cancelled.");

        var approvals = await harness.Client.GetFromJsonAsync<List<ApprovalEntry>>("/approvals", Json);

        var approval = Assert.Single(approvals!);
        Assert.Equal("rebook", approval.Tool);
        Assert.Equal(620, approval.Amount);
        Assert.Equal(300, approval.Limit);
        Assert.Equal(ApprovalOutcomes.Pending, approval.Outcome);
    }

    [Fact]
    public async Task GetApprovalsIsEmptyWhenNothingIsWaiting()
    {
        await using var harness = await Harness.StartAsync(UnderLimitBooking, UnderLimitFlight);
        await harness.StartRunAsync("My booking is BK-1001 and my flight was cancelled.");

        var approvals = await harness.Client.GetFromJsonAsync<List<ApprovalEntry>>("/approvals", Json);

        Assert.Empty(approvals!);
    }

    [Fact]
    public async Task PostApprovalApprovesAndTheRunCompletes()
    {
        await using var harness = await Harness.StartAsync(OverLimitBooking, OverLimitFlight);
        var runId = await harness.StartRunAsync("My booking is BK-1002 and my flight was cancelled.");
        var approvalId = harness.Store.Get(runId)!.PendingApproval!.ApprovalId;

        var response = await harness.Client.PostAsJsonAsync($"/approvals/{approvalId}", new { approved = true });
        await harness.Store.WhenSettledAsync(runId);

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var run = harness.Store.Get(runId)!;
        Assert.Equal(RunStates.Completed, run.State);
        Assert.Equal(ApprovalOutcomes.Approved, run.Outcome);
        Assert.True(harness.Tools.WasInvoked("rebook"));
    }

    /// <summary>
    /// The body is the decision, not a run snapshot. Answering restarts the workflow, so a
    /// run state read a moment later would depend on how far the resume had got.
    /// </summary>
    [Fact]
    public async Task PostApprovalAnswersWithTheDecisionItMade()
    {
        await using var harness = await Harness.StartAsync(OverLimitBooking, OverLimitFlight);
        var runId = await harness.StartRunAsync("My booking is BK-1002 and my flight was cancelled.");
        var approvalId = harness.Store.Get(runId)!.PendingApproval!.ApprovalId;

        var response = await harness.Client.PostAsJsonAsync($"/approvals/{approvalId}", new { approved = true });
        var answer = await response.Content.ReadFromJsonAsync<AnswerApprovalResponse>(Json);
        await harness.Store.WhenSettledAsync(runId);

        Assert.NotNull(answer);
        Assert.Equal(approvalId, answer.ApprovalId);
        Assert.Equal(runId, answer.RunId);
        Assert.True(answer.Approved);
        Assert.Equal(ApprovalOutcomes.Approved, answer.Outcome);
    }

    /// <summary>
    /// The rare path where the workflow does not hand its stream over within the bound: the
    /// decision the caller made is still the one reported, but the body says the run behind
    /// it did not survive rather than leaving that to a follow-up <c>GET /runs/{runId}</c>.
    /// </summary>
    [Fact]
    public async Task PostApprovalReportsWhenTheHandoverBoundFailedTheRunBehindIt()
    {
        var logger = new PausingLogger<RunStore>(RunStore.PendingApprovalLogMessage);
        await using var harness = await Harness.StartAsync(
            OverLimitBooking, OverLimitFlight, logger: logger, passHandover: TimeSpan.FromMilliseconds(50));

        var runId = await StartRunHeldAtTheApprovalAsync(harness, logger);
        var approvalId = harness.Store.Get(runId)!.PendingApproval!.ApprovalId;

        var response = await harness.Client.PostAsJsonAsync($"/approvals/{approvalId}", new { approved = true });
        var answer = await response.Content.ReadFromJsonAsync<AnswerApprovalResponse>(Json);

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.NotNull(answer);
        Assert.True(answer.RunFailed);
        Assert.Equal(ApprovalOutcomes.Approved, answer.Outcome);
        Assert.Equal(RunStates.Failed, harness.Store.Get(runId)!.State);

        logger.Release();
        await harness.Store.WhenSettledAsync(runId);
    }

    private static async Task<string> StartRunHeldAtTheApprovalAsync(Harness harness, PausingLogger<RunStore> logger)
    {
        var response = await harness.Client.PostAsJsonAsync("/runs", new { message = "My booking is BK-1002 and my flight was cancelled." });
        var started = (await response.Content.ReadFromJsonAsync<StartRunResponse>(Json))!;
        await logger.Reached.WaitAsync(TimeSpan.FromSeconds(10));
        return started.RunId;
    }

    [Fact]
    public async Task PostApprovalRejectsAndTheToolNeverRuns()
    {
        await using var harness = await Harness.StartAsync(OverLimitBooking, OverLimitFlight);
        var runId = await harness.StartRunAsync("My booking is BK-1002 and my flight was cancelled.");
        var approvalId = harness.Store.Get(runId)!.PendingApproval!.ApprovalId;

        var response = await harness.Client.PostAsJsonAsync($"/approvals/{approvalId}", new { approved = false });
        await harness.Store.WhenSettledAsync(runId);

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal(ApprovalOutcomes.Rejected, harness.Store.Get(runId)!.Outcome);
        Assert.False(harness.Tools.WasInvoked("rebook"));
    }

    [Fact]
    public async Task ASecondAnswerToTheSameApprovalIsAConflict()
    {
        await using var harness = await Harness.StartAsync(OverLimitBooking, OverLimitFlight);
        var runId = await harness.StartRunAsync("My booking is BK-1002 and my flight was cancelled.");
        var approvalId = harness.Store.Get(runId)!.PendingApproval!.ApprovalId;

        var first = await harness.Client.PostAsJsonAsync($"/approvals/{approvalId}", new { approved = true });
        await harness.Store.WhenSettledAsync(runId);
        var second = await harness.Client.PostAsJsonAsync($"/approvals/{approvalId}", new { approved = true });

        Assert.Equal(HttpStatusCode.OK, first.StatusCode);
        Assert.Equal(HttpStatusCode.Conflict, second.StatusCode);
    }

    [Fact]
    public async Task PostApprovalForAnUnknownIdIsNotFound()
    {
        await using var harness = await Harness.StartAsync(OverLimitBooking, OverLimitFlight);

        var response = await harness.Client.PostAsJsonAsync("/approvals/ap-nosuchthing", new { approved = true });

        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
    }

    [Fact]
    public async Task PostApprovalWithoutADecisionIsRejected()
    {
        await using var harness = await Harness.StartAsync(OverLimitBooking, OverLimitFlight);
        var runId = await harness.StartRunAsync("My booking is BK-1002 and my flight was cancelled.");
        var approvalId = harness.Store.Get(runId)!.PendingApproval!.ApprovalId;

        var response = await harness.Client.PostAsJsonAsync($"/approvals/{approvalId}", new { });

        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
    }

    private sealed record Harness(WebApplication App, HttpClient Client, RunStore Store, FakeRebookingTools Tools, Meter Meter)
        : IAsyncDisposable
    {
        public static async Task<Harness> StartAsync(
            string bookingRef,
            string flightId,
            ILogger<RunStore>? logger = null,
            TimeSpan? passHandover = null)
        {
            var tools = new FakeRebookingTools();
            var chatClient = new ScriptedAgentChatClient(
            [
                ScriptedAgentChatClient.ToolCall(
                    AgentSetup.HandoffToolName, ("reasonForHandoff", "the traveller's flight was cancelled")),
                ScriptedAgentChatClient.ToolCall("lookup_booking", ("booking_ref", bookingRef)),
                ScriptedAgentChatClient.ToolCall("rebook", ("booking_ref", bookingRef), ("flight_id", flightId)),
                ScriptedAgentChatClient.Reply("I have dealt with your booking."),
            ]);

            var options = new RunStoreOptions(
                ApprovalTimeoutSeconds: 600, RunTimeoutSeconds: 300, RunTtlSeconds: 3600);

            // Owned by this harness rather than the process, unlike Program.cs's meter: a
            // fresh test host builds a fresh one every time, and never disposing it would
            // leak one into the process-wide MeterListener registry per test.
            var meter = new Meter(Sources.AgentRebooking);

            var store = new RunStore(
                () => AgentSetup.BuildWorkflow(chatClient, tools.Tools),
                new ApprovalGate(new SeedPriceLookup(), RunHarness.ApprovalLimit),
                options,
                new ApprovalTelemetry(meter),
                TimeProvider.System,
                logger ?? NullLogger<RunStore>.Instance)
            {
                PassHandover = passHandover ?? TimeSpan.FromSeconds(5),
            };

            var builder = WebApplication.CreateSlimBuilder();
            builder.WebHost.UseTestServer();
            builder.Logging.ClearProviders();
            builder.Services.AddSingleton(store);

            var app = builder.Build();
            app.MapRunEndpoints();
            await app.StartAsync();

            return new Harness(app, app.GetTestClient(), store, tools, meter);
        }

        /// <summary>Posts a message and waits for the run to settle, pending or finished.</summary>
        public async Task<string> StartRunAsync(string message)
        {
            var response = await Client.PostAsJsonAsync("/runs", new { message });
            response.EnsureSuccessStatusCode();

            var started = (await response.Content.ReadFromJsonAsync<StartRunResponse>(Json))!;
            await Store.WhenSettledAsync(started.RunId);
            return started.RunId;
        }

        public async ValueTask DisposeAsync()
        {
            Client.Dispose();
            await App.StopAsync();
            await App.DisposeAsync();
            await Store.DisposeAsync();
            Meter.Dispose();
        }
    }
}
