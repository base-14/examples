using System.ComponentModel;
using System.IO.Pipelines;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using ModelContextProtocol.Client;
using ModelContextProtocol.Protocol;
using ModelContextProtocol.Server;

namespace AgentRebooking.Tests.Support;

/// <summary>
/// The same four tool names over a real in-process MCP session, with canned answers and no
/// Postgres behind them. <see cref="FakeRebookingTools"/> covers every run store test that
/// only needs a tool to run; this one exists for the telemetry of the MCP hop, which local
/// <see cref="AIFunctionFactory"/> functions cannot produce.
/// </summary>
/// <remarks>
/// The transport is the app's: two <see cref="Pipe"/> instances,
/// <c>WithStreamServerTransport</c> on the server and <c>StreamClientTransport</c> on the
/// client. A listener on <c>Experimental.ModelContextProtocol</c> has to be attached before
/// the client is created, because the SDK checks for one on every request.
/// </remarks>
internal sealed class StubMcpSession : IAsyncDisposable
{
    private readonly IHost _host;
    private readonly McpClient _client;
    private readonly Pipe _clientToServer;
    private readonly Pipe _serverToClient;

    private StubMcpSession(IHost host, McpClient client, Pipe clientToServer, Pipe serverToClient)
    {
        _host = host;
        _client = client;
        _clientToServer = clientToServer;
        _serverToClient = serverToClient;
    }

    public IReadOnlyList<AITool> Tools { get; private set; } = [];

    public static async Task<StubMcpSession> StartAsync(CancellationToken cancellationToken = default)
    {
        var clientToServer = new Pipe();
        var serverToClient = new Pipe();

        var builder = Host.CreateApplicationBuilder();
        builder.Logging.ClearProviders();
        builder.Services
            .AddMcpServer(o => o.ServerInfo = new Implementation { Name = "stub-rebooking-tools", Version = "0.1.0" })
            .WithStreamServerTransport(clientToServer.Reader.AsStream(), serverToClient.Writer.AsStream())
            .WithTools<StubRebookingTools>();

        var host = builder.Build();
        await host.StartAsync(cancellationToken);

        var transport = new StreamClientTransport(
            serverInput: clientToServer.Writer.AsStream(),
            serverOutput: serverToClient.Reader.AsStream());
        var client = await McpClient.CreateAsync(transport, cancellationToken: cancellationToken);

        var session = new StubMcpSession(host, client, clientToServer, serverToClient);
        session.Tools = [.. await client.ListToolsAsync(cancellationToken: cancellationToken)];
        return session;
    }

    public async ValueTask DisposeAsync()
    {
        await _client.DisposeAsync();
        await _host.StopAsync();
        _host.Dispose();

        await _clientToServer.Writer.CompleteAsync();
        await _clientToServer.Reader.CompleteAsync();
        await _serverToClient.Writer.CompleteAsync();
        await _serverToClient.Reader.CompleteAsync();
    }
}

[McpServerToolType]
public sealed class StubRebookingTools
{
    [McpServerTool(Name = "lookup_booking")]
    [Description("Look up a booking by its reference and return its route, date and status.")]
    public static object LookupBooking([Description("The booking reference")] string booking_ref) =>
        new { booking_ref, route = "LHR-BER", date = "2026-10-02", status = "cancelled" };

    [McpServerTool(Name = "search_alternatives")]
    [Description("List alternative flights and the hotel option available for a booking.")]
    public static object SearchAlternatives([Description("The booking reference")] string booking_ref) =>
        new { booking_ref, flights = Array.Empty<object>() };

    [McpServerTool(Name = "rebook")]
    [Description("Rebook the traveller's booking onto the given alternative flight.")]
    public static object Rebook(
        [Description("The booking reference")] string booking_ref,
        [Description("The flight id to rebook onto")] string flight_id) =>
        new { booking_ref, rebooked_to = flight_id, status = "confirmed" };

    [McpServerTool(Name = "add_hotel")]
    [Description("Add a hotel stay to the traveller's booking.")]
    public static object AddHotel(
        [Description("The booking reference")] string booking_ref,
        [Description("The hotel id to add")] string hotel_id) =>
        new { booking_ref, hotel_id, status = "confirmed" };
}
