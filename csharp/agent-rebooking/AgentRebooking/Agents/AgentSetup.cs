using AgentRebooking.Runs;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

namespace AgentRebooking.Agents;

/// <summary>
/// Builds the two-agent handoff workflow: triage classifies the traveller's message and
/// hands off to rebooking, which does the work through the MCP tools.
/// </summary>
public static class AgentSetup
{
    public const string TriageAgentId = "triage";
    public const string RebookingAgentId = "rebooking";

    /// <summary>
    /// The name of the tool the handoff builder injects into the triage agent. The prefix
    /// is <c>handoff_to_</c> and the suffix is a 1-based counter over that agent's handoff
    /// targets, so triage's single target is 1. The framework's own XML documentation and
    /// its default handoff instructions both claim <c>handoff_to_{agent_id}</c>; both are
    /// wrong at 1.21.0. Observed in ten of ten spike runs, see SPIKE-FINDINGS.md.
    /// </summary>
    public const string HandoffToolName = "handoff_to_1";

    private const string TriageInstructions =
        "You are a travel triage agent. For any message about a cancelled, delayed or disrupted flight, " +
        "hand off to the rebooking agent at once by calling the handoff tool. Do not answer the traveller yourself.";

    private const string RebookingInstructions =
        "You are a rebooking agent. Call lookup_booking with the traveller's booking reference, then " +
        "search_alternatives for that booking. Pick the cheapest alternative that keeps the traveller's travel " +
        "date and call rebook with the booking reference and that flight id. Call add_hotel only if the " +
        "traveller asks for a hotel. Then tell the traveller in one short paragraph what you did. " +
        "If a rebooking was not approved, tell the traveller the rebooking was not made.";

    /// <summary>
    /// Every call to these pauses the workflow, because
    /// <see cref="ApprovalRequiredAIFunction"/> carries no predicate. Whether a paused call
    /// needs a human is decided afterwards by <see cref="ApprovalGate"/>, against a price
    /// read from Postgres.
    /// </summary>
    /// <remarks>
    /// Taken from the gate rather than written out again. The tools that pause are exactly
    /// the tools the gate can price, so a name added to one and not the other would either
    /// hang a call nothing can decide or let a spend through with no gate at all.
    /// </remarks>
    public static readonly string[] ApprovalRequiredTools = [ApprovalGate.RebookTool, ApprovalGate.AddHotelTool];

    /// <summary>
    /// The workflow is cheap to build and holds per-run executor state, so callers build a
    /// fresh one for each traveller message rather than sharing one across runs.
    /// </summary>
    /// <param name="captureMessageContent">
    /// OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT. True puts the traveller's messages,
    /// the model's replies and the tool arguments on the chat and agent spans as attributes,
    /// where a backend will keep them. Off by default. The framework reads the same variable
    /// itself; it is passed explicitly so the app's one options object stays the only place
    /// the setting is read from.
    /// </param>
    public static Workflow BuildWorkflow(
        IChatClient chatClient, IEnumerable<AITool> tools, bool captureMessageContent = false)
    {
        var triage = new ChatClientAgent(
                chatClient,
                new ChatClientAgentOptions
                {
                    Id = TriageAgentId,
                    Name = TriageAgentId,
                    Description = "Classifies traveller messages and routes disruptions to rebooking.",
                    // ChatClientAgentOptions has no Instructions property at 1.21.0.
                    ChatOptions = new ChatOptions { Instructions = TriageInstructions },
                })
            .AsBuilder().UseOpenTelemetry(configure: Capture(captureMessageContent)).Build();

        var rebooking = new ChatClientAgent(
                chatClient,
                new ChatClientAgentOptions
                {
                    Id = RebookingAgentId,
                    Name = RebookingAgentId,
                    Description = "Rebooks travellers onto alternative flights and adds hotel stays.",
                    ChatOptions = new ChatOptions
                    {
                        Instructions = RebookingInstructions,
                        Tools = [.. tools.Select(WrapIfApprovalRequired)],
                        // One tool call per turn, so a run has at most one approval
                        // outstanding at a time. The handoff builder already forces this on
                        // triage; rebooking has no handoff targets, so it is set here.
                        AllowMultipleToolCalls = false,
                    },
                })
            .AsBuilder().UseOpenTelemetry(configure: Capture(captureMessageContent)).Build();

        return AgentWorkflowBuilder.CreateHandoffBuilderWith(triage)
            .WithHandoff(triage, rebooking)
            .EmitAgentResponseEvents()
            .Build();
    }

    private static Action<OpenTelemetryAgent> Capture(bool captureMessageContent) =>
        agent => agent.EnableSensitiveData = captureMessageContent;

    private static AITool WrapIfApprovalRequired(AITool tool) =>
        tool is AIFunction function && ApprovalRequiredTools.Contains(tool.Name)
            ? new ApprovalRequiredAIFunction(function)
            : tool;
}
