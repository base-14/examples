using System.ComponentModel;
using AgentRebooking.Data;
using ModelContextProtocol;
using ModelContextProtocol.Server;

namespace AgentRebooking.Mcp;

/// <summary>
/// The four tools the rebooking agent calls over MCP. Parameter names are snake_case on
/// purpose -- they become the JSON argument names the model fills in, and the design
/// fixes them as <c>booking_ref</c>, <c>flight_id</c> and <c>hotel_id</c>.
/// </summary>
[McpServerToolType]
public sealed class RebookingTools(BookingStore store)
{
    [McpServerTool(Name = "lookup_booking")]
    [Description("Look up a booking by its reference and return its route, date and status.")]
    public async Task<object> LookupBooking(
        [Description("The booking reference, for example BK-1001")] string booking_ref,
        CancellationToken cancellationToken)
    {
        var booking = await store.GetBookingAsync(booking_ref, cancellationToken);
        if (booking is null)
        {
            // McpException, not a returned error object: the SDK turns it into a result
            // with IsError set, so the model and the execute_tool span both see a failure
            // instead of a successful call that happens to carry an error message.
            throw new McpException($"No booking found for reference '{booking_ref}'.");
        }

        return new
        {
            booking_ref = booking.BookingRef,
            route = booking.Route,
            date = booking.TravelDate.ToString("yyyy-MM-dd"),
            status = booking.Status,
        };
    }

    [McpServerTool(Name = "search_alternatives")]
    [Description("List alternative flights and the hotel option available for a booking.")]
    public async Task<object> SearchAlternatives(
        [Description("The booking reference, for example BK-1001")] string booking_ref,
        CancellationToken cancellationToken)
    {
        var alternatives = await store.ListAlternativesAsync(booking_ref, cancellationToken);

        return new
        {
            booking_ref,
            alternatives = alternatives.Flights.Select(f => new { flight_id = f.FlightId, price = f.Price }),
            hotel = alternatives.Hotel is { } hotel
                ? new { hotel_id = hotel.HotelId, city = hotel.City, price = hotel.Price }
                : null,
        };
    }

    [McpServerTool(Name = "rebook")]
    [Description("Rebook the traveller's booking onto the given alternative flight.")]
    public async Task<object> Rebook(
        [Description("The booking reference")] string booking_ref,
        [Description("The flight id to rebook onto")] string flight_id,
        CancellationToken cancellationToken)
    {
        try
        {
            await store.ApplyRebookingAsync(booking_ref, flight_id, cancellationToken);
        }
        catch (InvalidOperationException ex)
        {
            throw new McpException(ex.Message);
        }

        return new { booking_ref, rebooked_to = flight_id, status = "confirmed" };
    }

    [McpServerTool(Name = "add_hotel")]
    [Description("Add a hotel stay to the traveller's booking.")]
    public async Task<object> AddHotel(
        [Description("The booking reference")] string booking_ref,
        [Description("The hotel id to add")] string hotel_id,
        CancellationToken cancellationToken)
    {
        try
        {
            await store.AddHotelAsync(booking_ref, hotel_id, cancellationToken);
        }
        catch (InvalidOperationException ex)
        {
            throw new McpException(ex.Message);
        }

        return new { booking_ref, hotel_id, status = "confirmed" };
    }
}
