using AgentRebooking.Runs;

namespace AgentRebooking.Tests.Support;

/// <summary>
/// The three seeded bookings and their prices, held in memory, so gate and run store
/// tests exercise the decision logic without a Postgres container. The production
/// lookup is <see cref="BookingStorePriceLookup"/>; the container-backed tests in
/// <c>ApprovalGateTests</c> cover that one against the real seed rows.
/// </summary>
internal sealed class SeedPriceLookup : IPriceLookup
{
    private static readonly Dictionary<(string Booking, string Flight), int> Flights = new()
    {
        [("BK-1001", "FL-201")] = 180,
        [("BK-1001", "FL-202")] = 240,
        [("BK-1002", "FL-301")] = 620,
        [("BK-1002", "FL-302")] = 710,
        [("BK-1003", "FL-401")] = 95,
    };

    private static readonly Dictionary<(string Booking, string Hotel), int> Hotels = new()
    {
        [("BK-1001", "HTL-BER")] = 120,
        [("BK-1002", "HTL-JFK")] = 210,
        [("BK-1003", "HTL-CDG")] = 140,
    };

    /// <summary>Every booking and flight this prices, for <c>SeedPriceLookupTests</c> to
    /// compare with the seed. Without it a pair invented here, and so present in neither
    /// the seed nor any query the test derives from it, would never be looked at.</summary>
    public static IReadOnlyCollection<(string Booking, string Flight)> FlightKeys => Flights.Keys;

    /// <inheritdoc cref="FlightKeys"/>
    public static IReadOnlyCollection<(string Booking, string Hotel)> HotelKeys => Hotels.Keys;

    public Task<int?> GetFlightPriceAsync(
        string bookingRef, string flightId, CancellationToken cancellationToken = default) =>
        Task.FromResult(Flights.TryGetValue((bookingRef, flightId), out var price) ? price : (int?)null);

    public Task<int?> GetHotelPriceAsync(
        string bookingRef, string hotelId, CancellationToken cancellationToken = default) =>
        Task.FromResult(Hotels.TryGetValue((bookingRef, hotelId), out var price) ? price : (int?)null);
}
