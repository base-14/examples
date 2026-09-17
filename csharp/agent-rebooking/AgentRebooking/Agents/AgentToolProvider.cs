using AgentRebooking.Data;
using AgentRebooking.Mcp;
using Microsoft.Extensions.AI;

namespace AgentRebooking.Agents;

/// <summary>
/// Opens the in-process MCP session once the host starts and holds the tool list the
/// rebooking agent is built from. One session serves the process.
/// </summary>
/// <remarks>
/// This is a hosted service, and registered after <c>AddOpenTelemetry</c>, so that the
/// session opens after the tracer provider has registered its listeners. The MCP SDK gates
/// its instrumentation on <c>ActivitySource.HasListeners()</c> for
/// <c>Experimental.ModelContextProtocol</c> at the start of every request, so a session
/// opened before the provider existed would silently lose the <c>server/discover</c> and
/// <c>tools/list</c> spans and the trace context in <c>params._meta</c>.
/// </remarks>
public sealed class AgentToolProvider(BookingStore store, ILogger<AgentToolProvider> logger)
    : IHostedService, IAsyncDisposable
{
    private McpHosting? _hosting;
    private IReadOnlyList<AITool>? _tools;

    /// <summary>
    /// The tool list, published only once the session is open and non-empty. Kestrel starts
    /// accepting requests before this hosted service has finished, and a request landing in
    /// that window would otherwise build a rebooking agent with no tools and produce a
    /// plausible run that called nothing. Failing the run is the honest answer.
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

        // Written after the list is fully built, read through Volatile.Read on the run
        // threads: the property is set here on the startup thread and read from others.
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
