using System.Text.Json;
using AgentRebooking.Mcp;
using AgentRebooking.Tests.Support;
using ModelContextProtocol.Protocol;

namespace AgentRebooking.Tests;

/// <summary>
/// <see cref="RebookingTools"/> reached through a real in-process <see cref="McpHosting"/>
/// client, backed by the same Testcontainers Postgres as <see cref="BookingStoreTests"/>.
/// Skips with a reason on a machine with no reachable Docker daemon; runs for real the
/// moment Docker returns. See <see cref="Support.DockerRequiredFactAttribute"/>.
/// </summary>
[Collection(PostgresCollection.Name)]
public sealed class RebookingToolsTests(PostgresFixture fixture)
{
    /// <summary>
    /// Order-independent on purpose: the server returns tools in dictionary enumeration
    /// order and neither it nor the client sorts, so the wire order is an implementation
    /// detail and asserting a sequence would make this test fail on an unrelated change.
    /// </summary>
    [DockerRequiredFact]
    public async Task ListTools_ReturnsTheFourRebookingTools()
    {
        await using var hosting = await McpHosting.StartAsync(fixture.Store);

        var tools = await hosting.Client.ListToolsAsync();

        Assert.Equal(
            ["add_hotel", "lookup_booking", "rebook", "search_alternatives"],
            tools.Select(t => t.Name).OrderBy(name => name, StringComparer.Ordinal));
    }

    [DockerRequiredFact]
    public async Task LookupBooking_BK1001_ReturnsItsRoute()
    {
        await using var hosting = await McpHosting.StartAsync(fixture.Store);

        var result = await hosting.Client.CallToolAsync(
            "lookup_booking", new Dictionary<string, object?> { ["booking_ref"] = "BK-1001" });

        var text = Assert.IsType<TextContentBlock>(Assert.Single(result.Content)).Text;
        using var document = JsonDocument.Parse(text);
        Assert.Equal("LHR-BER", document.RootElement.GetProperty("route").GetString());
    }

    /// <summary>
    /// An unknown booking must reach the caller as a failed tool call. Returning an error
    /// object with a successful result would leave <c>IsError</c> false, so both the model
    /// and the execute_tool span would record the call as having worked.
    /// </summary>
    [DockerRequiredFact]
    public async Task LookupBooking_UnknownRef_ReturnsAnErrorResult()
    {
        await using var hosting = await McpHosting.StartAsync(fixture.Store);

        var result = await hosting.Client.CallToolAsync(
            "lookup_booking", new Dictionary<string, object?> { ["booking_ref"] = "BK-0000" });

        Assert.True(result.IsError);
    }
}
