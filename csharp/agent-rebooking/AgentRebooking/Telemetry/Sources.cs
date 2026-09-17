using System.Diagnostics;

namespace AgentRebooking.Telemetry;

/// <summary>
/// Every activity source and meter name this example registers, and the one
/// <see cref="ActivitySource"/> it opens its own spans from. Program.cs registers from these
/// lists and the tests listen on them, so a name dropped here is also dropped from the tests.
/// </summary>
internal static class Sources
{
    /// <summary>The example's own source and meter. Both carry this one name.</summary>
    public const string AgentRebooking = "AgentRebooking";

    /// <summary>Gives <c>invoke_agent</c>, <c>chat</c> and <c>execute_tool</c>.</summary>
    public const string AgentFramework = "Experimental.Microsoft.Agents.AI";

    /// <summary>
    /// Gives the MCP spans, and is load-bearing beyond that: the SDK checks
    /// <c>ActivitySource.HasListeners()</c> on this exact name before it instruments anything.
    /// Without a listener, <c>execute_tool</c> silently loses every <c>mcp.*</c> attribute and
    /// <c>params._meta</c> loses <c>traceparent</c>.
    /// </summary>
    public const string ModelContextProtocol = "Experimental.ModelContextProtocol";

    /// <summary>Npgsql's built-in source and meter, which need only a listener.</summary>
    public const string Npgsql = "Npgsql";

    /// <summary>
    /// <c>Microsoft.Agents.AI.Workflows</c> is absent on purpose: its spans are gated behind
    /// <c>WorkflowBuilder.WithOpenTelemetry</c>, which the handoff builder does not expose at
    /// 1.21.0. ASP.NET Core and HttpClient register their own sources.
    /// </summary>
    public static readonly string[] TraceSourceNames =
        [AgentRebooking, AgentFramework, ModelContextProtocol, Npgsql];

    /// <inheritdoc cref="TraceSourceNames"/>
    public static readonly string[] MeterNames =
        [AgentRebooking, AgentFramework, ModelContextProtocol, Npgsql];

    public static readonly ActivitySource Activity = new(AgentRebooking);
}
