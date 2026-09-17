using System.IO.Pipelines;
using AgentRebooking.Data;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using ModelContextProtocol.Client;
using ModelContextProtocol.Protocol;

namespace AgentRebooking.Mcp;

/// <summary>
/// Hosts <see cref="RebookingTools"/> as an MCP server over two in-memory
/// <see cref="Pipe"/> instances and exposes a single <see cref="McpClient"/> the app uses
/// to reach it. No network port opens; server and client share the process.
/// </summary>
public sealed class McpHosting : IAsyncDisposable
{
    private readonly IHost _host;
    private readonly Pipe _clientToServer;
    private readonly Pipe _serverToClient;

    private McpHosting(IHost host, McpClient client, Pipe clientToServer, Pipe serverToClient)
    {
        _host = host;
        Client = client;
        _clientToServer = clientToServer;
        _serverToClient = serverToClient;
    }

    public McpClient Client { get; }

    public static async Task<McpHosting> StartAsync(BookingStore store, CancellationToken cancellationToken = default)
    {
        var clientToServer = new Pipe();
        var serverToClient = new Pipe();

        var builder = Host.CreateApplicationBuilder();
        builder.Logging.ClearProviders();
        // The store is owned by the caller: DisposeAsync below never touches it.
        builder.Services.AddSingleton(store);
        builder.Services
            .AddMcpServer(o => o.ServerInfo = new Implementation { Name = "rebooking-tools", Version = "0.1.0" })
            .WithStreamServerTransport(clientToServer.Reader.AsStream(), serverToClient.Writer.AsStream())
            .WithTools<RebookingTools>();

        var host = builder.Build();
        await host.StartAsync(cancellationToken);

        try
        {
            var clientTransport = new StreamClientTransport(
                serverInput: clientToServer.Writer.AsStream(),
                serverOutput: serverToClient.Reader.AsStream());
            var client = await McpClient.CreateAsync(clientTransport, cancellationToken: cancellationToken);

            return new McpHosting(host, client, clientToServer, serverToClient);
        }
        catch
        {
            await host.StopAsync(cancellationToken);
            host.Dispose();
            await CompleteAsync(clientToServer, serverToClient);
            throw;
        }
    }

    public async ValueTask DisposeAsync()
    {
        await Client.DisposeAsync();
        await _host.StopAsync();
        _host.Dispose();

        await CompleteAsync(_clientToServer, _serverToClient);
    }

    private static async Task CompleteAsync(Pipe clientToServer, Pipe serverToClient)
    {
        await clientToServer.Writer.CompleteAsync();
        await clientToServer.Reader.CompleteAsync();
        await serverToClient.Writer.CompleteAsync();
        await serverToClient.Reader.CompleteAsync();
    }
}
