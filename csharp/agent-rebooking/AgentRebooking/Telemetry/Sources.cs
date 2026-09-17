using System.Diagnostics;

namespace AgentRebooking.Telemetry;

/// <summary>
/// Every activity source and meter name this example registers, and the one
/// <see cref="ActivitySource"/> it opens its own spans from. Program.cs registers from these
/// lists and the tests listen on them, so a name that stops being registered also stops
/// being asserted on rather than quietly changing what the app exports.
/// </summary>
internal static class Sources
{
    /// <summary>The example's own source and meter. Both carry this one name.</summary>
    public const string AgentRebooking = "AgentRebooking";

    /// <summary>Gives <c>invoke_agent</c>, <c>chat</c> and <c>execute_tool</c>.</summary>
    public const string AgentFramework = "Experimental.Microsoft.Agents.AI";

    /// <summary>
    /// Gives <c>server/discover</c>, <c>tools/list</c> and the <c>tools/call {tool}</c> server
    /// span, and is load-bearing beyond that. The MCP C# SDK checks
    /// <c>ActivitySource.HasListeners()</c> for this exact name before it instruments
    /// anything: without a listener the <c>execute_tool</c> span loses every <c>mcp.*</c>
    /// attribute and <c>params._meta</c> loses <c>traceparent</c>, with no error and no log
    /// line. TelemetryTests listens on this list for that reason.
    /// </summary>
    public const string ModelContextProtocol = "Experimental.ModelContextProtocol";

    /// <summary>Npgsql's built-in source and meter, which need only a listener to switch on.</summary>
    public const string Npgsql = "Npgsql";

    /// <summary>
    /// <c>Microsoft.Agents.AI.Workflows</c> is deliberately absent. Its spans are gated behind
    /// <c>WorkflowBuilder.WithOpenTelemetry</c>, which the handoff builder does not expose at
    /// 1.21.0, so registering it would add a name that can never produce a span. ASP.NET Core
    /// and HttpClient are absent too: their instrumentation packages register their own sources.
    /// </summary>
    public static readonly string[] TraceSourceNames =
        [AgentRebooking, AgentFramework, ModelContextProtocol, Npgsql];

    /// <inheritdoc cref="TraceSourceNames"/>
    public static readonly string[] MeterNames =
        [AgentRebooking, AgentFramework, ModelContextProtocol, Npgsql];

    public static readonly ActivitySource Activity = new(AgentRebooking);
}
