using AgentRebooking.Data;
using AgentRebooking.Mcp;
using Microsoft.Extensions.AI;

namespace AgentRebooking.Agents;

/// <summary>
/// Opens the in-process MCP session once the host starts and holds the tool list the
/// rebooking agent is built from. One session serves the process.
/// </summary>
/// <remarks>
/// Registered after <c>AddOpenTelemetry</c> so the session opens once the tracer provider's
/// listeners exist. The MCP SDK gates its instrumentation on
/// <c>ActivitySource.HasListeners()</c>, so a session opened first loses its spans silently.
/// </remarks>
public sealed class AgentToolProvider(BookingStore store, ILogger<AgentToolProvider> logger)
    : IHostedService, IAsyncDisposable
{
    private McpHosting? _hosting;
    private IReadOnlyList<AITool>? _tools;

    /// <summary>
    /// Published only once the session is open and non-empty. Kestrel accepts requests before
    /// this hosted service finishes, and a run in that window would otherwise build an agent
    /// with no tools and answer plausibly without calling anything.
    /// </summary>
    public IReadOnlyList<AITool> Tools => Volatile.Read(ref _tools)
        ?? throw new InvalidOperationException(
            "The MCP session is not open yet, so there are no tools to build an agent with.");

    public async Task StartAsync(CancellationToken cancellationToken)
    {
        _hosting = await McpHosting.StartAsync(store, cancellationToken);
        IReadOnlyList<AITool> tools =
            [.. await _hosting.Client.ListToolsAsync(cancellationToken: cancellationToken)];

        if (tools.Count == 0)
        {
            throw new InvalidOperationException(
                "The MCP server exposed no tools, so the rebooking agent would have nothing to call.");
        }

        Volatile.Write(ref _tools, tools);

        logger.LogInformation(
            "MCP tools available: {Tools}", string.Join(", ", tools.Select(tool => tool.Name)));
    }

    public Task StopAsync(CancellationToken cancellationToken) => Task.CompletedTask;

    public async ValueTask DisposeAsync()
    {
        if (_hosting is not null)
        {
            await _hosting.DisposeAsync();
            _hosting = null;
        }
    }
}
