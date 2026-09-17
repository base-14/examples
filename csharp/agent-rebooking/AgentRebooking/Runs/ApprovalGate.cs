using System.Text.Json;
using AgentRebooking.Data;
using Microsoft.Extensions.AI;

namespace AgentRebooking.Runs;

/// <summary>
/// Prices one offer belonging to one booking. No method here takes a price, so a number the
/// model wrote into a tool call can never become the amount the limit is checked against.
/// </summary>
public interface IPriceLookup
{
    Task<int?> GetFlightPriceAsync(string bookingRef, string flightId, CancellationToken cancellationToken = default);

    Task<int?> GetHotelPriceAsync(string bookingRef, string hotelId, CancellationToken cancellationToken = default);
}

/// <summary>
/// The production lookup, onto the Postgres-backed <see cref="BookingStore"/>. Both store
/// methods are scoped to the booking and return null for an id outside it.
/// </summary>
public sealed class BookingStorePriceLookup(BookingStore store) : IPriceLookup
{
    public Task<int?> GetFlightPriceAsync(
        string bookingRef, string flightId, CancellationToken cancellationToken = default) =>
        store.GetFlightPriceAsync(bookingRef, flightId, cancellationToken);

    public Task<int?> GetHotelPriceAsync(
        string bookingRef, string hotelId, CancellationToken cancellationToken = default) =>
        store.GetHotelPriceAsync(bookingRef, hotelId, cancellationToken);
}

/// <param name="AutoApprove">True when the app answers the workflow itself, without a human.</param>
/// <param name="Amount">The server-side price, or null when the call named no price-able offer.</param>
/// <param name="Reason">Short text for the approvals list and the logs.</param>
public sealed record ApprovalDecision(
    bool AutoApprove,
    string Tool,
    string? BookingRef,
    string? OfferId,
    int? Amount,
    int Limit,
    string Reason);

/// <summary>
/// Decides whether a paused tool call can be answered by the app or has to wait for a human.
/// Fails closed: anything the gate cannot price server-side goes to a human.
/// </summary>
public sealed class ApprovalGate(IPriceLookup prices, int limit)
{
    public const string RebookTool = "rebook";
    public const string AddHotelTool = "add_hotel";

    public async Task<ApprovalDecision> DecideAsync(
        FunctionCallContent call, CancellationToken cancellationToken = default)
    {
        var bookingRef = ReadArgument(call, "booking_ref");

        var offerId = call.Name switch
        {
            RebookTool => ReadArgument(call, "flight_id"),
            AddHotelTool => ReadArgument(call, "hotel_id"),
            _ => null,
        };

        if (call.Name is not (RebookTool or AddHotelTool))
        {
            return Pending(call, bookingRef, offerId, null, $"'{call.Name}' is not a tool this gate can price");
        }

        if (bookingRef is null || offerId is null)
        {
            return Pending(call, bookingRef, offerId, null, "the call did not name both a booking and an offer");
        }

        var amount = call.Name == RebookTool
            ? await prices.GetFlightPriceAsync(bookingRef, offerId, cancellationToken)
            : await prices.GetHotelPriceAsync(bookingRef, offerId, cancellationToken);

        if (amount is null)
        {
            return Pending(call, bookingRef, offerId, null, $"'{offerId}' is not an offer on booking '{bookingRef}'");
        }

        return amount <= limit
            ? new ApprovalDecision(true, call.Name, bookingRef, offerId, amount, limit, $"{amount} is within the limit of {limit}")
            : Pending(call, bookingRef, offerId, amount, $"{amount} is over the limit of {limit}");
    }

    private ApprovalDecision Pending(
        FunctionCallContent call, string? bookingRef, string? offerId, int? amount, string reason) =>
        new(false, call.Name, bookingRef, offerId, amount, limit, reason);

    // Strings when the app builds the call, JsonElement when it came off the wire.
    private static string? ReadArgument(FunctionCallContent call, string name)
    {
        if (call.Arguments is null || !call.Arguments.TryGetValue(name, out var value))
        {
            return null;
        }

        var text = value switch
        {
            string s => s,
            JsonElement { ValueKind: JsonValueKind.String } element => element.GetString(),
            null => null,
            _ => value.ToString(),
        };

        return string.IsNullOrWhiteSpace(text) ? null : text;
    }
}
