using AgentRebooking.Runs;

namespace AgentRebooking.Api;

/// <param name="Message">The traveller's message, which has to carry a booking reference.</param>
public sealed record StartRunRequest(string? Message);

public sealed record StartRunResponse(string RunId, string State);

/// <param name="Approved">True to let the tool run, false to tell the agent it was refused.</param>
public sealed record AnswerApprovalRequest(bool? Approved);

/// <summary>
/// What an accepted answer did. Not a run snapshot: answering restarts the workflow, so poll
/// <c>GET /runs/{runId}</c> for the state.
/// </summary>
/// <param name="RunFailed">
/// True on the rare path where the workflow did not hand its stream over in time. The decision
/// was still made and is recorded against the approval.
/// </param>
public sealed record AnswerApprovalResponse(string ApprovalId, string? RunId, bool Approved, string Outcome, bool RunFailed);

/// <summary>The four run endpoints. Health is mapped in Program.cs.</summary>
public static class RunEndpoints
{
    public static IEndpointRouteBuilder MapRunEndpoints(this IEndpointRouteBuilder endpoints)
    {
        // Accepted, not Created: the run carries on in the background.
        endpoints.MapPost("/runs", (StartRunRequest request, RunStore store) =>
        {
            if (string.IsNullOrWhiteSpace(request.Message))
            {
                return Results.Problem("A run needs a non-empty message.", statusCode: StatusCodes.Status400BadRequest);
            }

            var runId = store.Start(request.Message);
            return Results.Accepted($"/runs/{runId}", new StartRunResponse(runId, RunStates.Running));
        });

        endpoints.MapGet("/runs/{runId}", (string runId, RunStore store) =>
            store.Get(runId) is { } run
                ? Results.Ok(run)
                : Results.Problem($"No run '{runId}'.", statusCode: StatusCodes.Status404NotFound));

        endpoints.MapGet("/approvals", (RunStore store) => Results.Ok(store.ListPendingApprovals()));

        endpoints.MapPost("/approvals/{approvalId}", async (
            string approvalId, AnswerApprovalRequest request, RunStore store) =>
        {
            if (request.Approved is not { } approved)
            {
                return Results.Problem(
                    "An answer needs 'approved' to be true or false.", statusCode: StatusCodes.Status400BadRequest);
            }

            // Read before answering: the answer clears the pending request.
            var runId = store.FindRunIdForApproval(approvalId);
            var result = await store.AnswerAsync(approvalId, approved);

            return result switch
            {
                AnswerResult.NotFound => Results.Problem(
                    $"No approval '{approvalId}'.", statusCode: StatusCodes.Status404NotFound),
                AnswerResult.Conflict => Results.Problem(
                    $"Approval '{approvalId}' has already been answered or its run has finished.",
                    statusCode: StatusCodes.Status409Conflict),
                // Read after answering, so a handover-bound failure is already reflected.
                _ => Results.Ok(new AnswerApprovalResponse(
                    approvalId,
                    runId,
                    approved,
                    approved ? ApprovalOutcomes.Approved : ApprovalOutcomes.Rejected,
                    RunFailed: runId is not null && store.Get(runId)?.State == RunStates.Failed)),
            };
        });

        return endpoints;
    }
}
