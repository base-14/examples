using System.Text.Json;
using Microsoft.Extensions.AI;

namespace AgentRebooking.Tests.Support;

/// <summary>
/// The four tool names the real MCP server exposes, as local functions that record their
/// arguments, so the run store tests exercise the workflow without Postgres or a container.
/// <c>RebookingToolsTests</c> and <c>TelemetryTests</c> cover what crosses MCP.
/// </summary>
internal sealed class FakeRebookingTools
{
    private readonly Lock _sync = new();
    private readonly List<string> _invocations = [];

    public FakeRebookingTools()
    {
        Tools =
        [
            AIFunctionFactory.Create(
                (string booking_ref) =>
                {
                    Record("lookup_booking", booking_ref);
                    return JsonSerializer.Serialize(new
                    {
                        booking_ref,
                        route = "LHR-BER",
                        date = "2026-10-02",
                        status = "cancelled",
                    });
                },
                "lookup_booking",
                "Look up a booking by its reference."),

            AIFunctionFactory.Create(
                (string booking_ref) =>
                {
                    Record("search_alternatives", booking_ref);
                    return JsonSerializer.Serialize(new { booking_ref, alternatives = Array.Empty<object>() });
                },
                "search_alternatives",
                "List alternative flights for a booking."),

            AIFunctionFactory.Create(
                (string booking_ref, string flight_id) =>
                {
                    Record("rebook", booking_ref, flight_id);
                    return JsonSerializer.Serialize(new { booking_ref, rebooked_to = flight_id, status = "confirmed" });
                },
                "rebook",
                "Rebook the traveller onto an alternative flight."),

            AIFunctionFactory.Create(
                (string booking_ref, string hotel_id) =>
                {
                    Record("add_hotel", booking_ref, hotel_id);
                    return JsonSerializer.Serialize(new { booking_ref, hotel_id, status = "confirmed" });
                },
                "add_hotel",
                "Add a hotel stay to the traveller's booking."),
        ];
    }

    public IReadOnlyList<AITool> Tools { get; }

    /// <summary>Every tool that actually ran, in order, as "name arg arg".</summary>
    public IReadOnlyList<string> Invocations
    {
        get
        {
            lock (_sync)
            {
                return [.. _invocations];
            }
        }
    }

    public bool WasInvoked(string toolName) =>
        Invocations.Any(invocation => invocation.StartsWith(toolName, StringComparison.Ordinal));

    private void Record(string toolName, params string[] arguments)
    {
        lock (_sync)
        {
            _invocations.Add(string.Join(' ', [toolName, .. arguments]));
        }
    }
}
