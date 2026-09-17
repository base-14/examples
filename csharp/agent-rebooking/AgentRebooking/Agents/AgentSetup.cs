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
    /// The tool the handoff builder injects into triage. The suffix is a 1-based counter over
    /// the agent's handoff targets, not the target's id: the framework's own documentation
    /// says <c>handoff_to_{agent_id}</c>, which 1.21.0 does not emit.
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
    /// Every call to these pauses the workflow, because <see cref="ApprovalRequiredAIFunction"/>
    /// carries no predicate. <see cref="ApprovalGate"/> then decides, against a price read from
    /// Postgres. Taken from the gate so the set that pauses and the set it can price cannot drift.
    /// </summary>
    public static readonly string[] ApprovalRequiredTools = [ApprovalGate.RebookTool, ApprovalGate.AddHotelTool];

    /// <summary>
    /// The workflow is cheap to build and holds per-run executor state, so callers build a
    /// fresh one for each traveller message rather than sharing one across runs.
    /// </summary>
    /// <param name="captureMessageContent">
    /// OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT. True puts traveller messages, model
    /// replies and tool arguments on the chat and agent spans. Passed explicitly, though the
    /// framework reads the variable itself, so the app's options object stays the single reader.
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
                        // One tool call per turn, so a run has at most one approval outstanding.
                        // The handoff builder already forces this on triage.
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
