using AgentRebooking.Tests.Support;

namespace AgentRebooking.Tests;

/// <summary>
/// <see cref="AgentRebooking.Data.BookingStore"/> against a real Postgres 18 from
/// Testcontainers, schema and seed applied exactly as the app applies them at startup.
/// Skips with a reason on a machine with no reachable Docker daemon; runs for real the
/// moment Docker returns. See <see cref="Support.DockerRequiredFactAttribute"/>.
/// </summary>
[Collection(PostgresCollection.Name)]
public sealed class BookingStoreTests(PostgresFixture fixture)
{
    [DockerRequiredFact]
    public async Task GetBooking_KnownRef_ReturnsSeedRow()
    {
        var booking = await fixture.Store.GetBookingAsync("BK-1001");

        Assert.NotNull(booking);
        Assert.Equal("LHR-BER", booking!.Route);
        Assert.Equal(new DateOnly(2026, 10, 2), booking.TravelDate);
    }

    [DockerRequiredFact]
    public async Task GetBooking_EveryOtherSeedRow_MatchesTheDesign()
    {
        var overLimit = await fixture.Store.GetBookingAsync("BK-1002");
        var singleOption = await fixture.Store.GetBookingAsync("BK-1003");

        Assert.Equal("LHR-JFK", overLimit!.Route);
        Assert.Equal(new DateOnly(2026, 10, 2), overLimit.TravelDate);

        Assert.Equal("LHR-CDG", singleOption!.Route);
        Assert.Equal(new DateOnly(2026, 10, 3), singleOption.TravelDate);
    }

    [DockerRequiredFact]
    public async Task GetBooking_UnknownRef_ReturnsNull()
    {
        Assert.Null(await fixture.Store.GetBookingAsync("BK-0000"));
    }

    [DockerRequiredFact]
    public async Task ListAlternatives_UnderLimitBooking_ReturnsBothFlightsAndTheHotel()
    {
        var alternatives = await fixture.Store.ListAlternativesAsync("BK-1001");

        Assert.Collection(
            alternatives.Flights,
            f => Assert.Equal(("FL-201", 180), (f.FlightId, f.Price)),
            f => Assert.Equal(("FL-202", 240), (f.FlightId, f.Price)));
        Assert.Equal(
            ("HTL-BER", "Berlin", 120),
            (alternatives.Hotel!.HotelId, alternatives.Hotel.City, alternatives.Hotel.Price));
    }

    [DockerRequiredFact]
    public async Task ListAlternatives_OverLimitBooking_EveryOptionExceeds300()
    {
        var alternatives = await fixture.Store.ListAlternativesAsync("BK-1002");

        Assert.All(alternatives.Flights, f => Assert.True(f.Price > 300));
        Assert.Equal(210, alternatives.Hotel!.Price);
    }

    [DockerRequiredFact]
    public async Task ListAlternatives_SingleOptionBooking_ReturnsOneFlight()
    {
        var alternatives = await fixture.Store.ListAlternativesAsync("BK-1003");

        var flight = Assert.Single(alternatives.Flights);
        Assert.Equal(("FL-401", 95), (flight.FlightId, flight.Price));
    }

    [DockerRequiredFact]
    public async Task GetFlightPrice_AlternativeOfThatBooking_ReturnsTheSeededPrice()
    {
        Assert.Equal(180, await fixture.Store.GetFlightPriceAsync("BK-1001", "FL-201"));
        Assert.Equal(620, await fixture.Store.GetFlightPriceAsync("BK-1002", "FL-301"));
    }

    [DockerRequiredFact]
    public async Task GetFlightPrice_UnknownId_ReturnsNull()
    {
        Assert.Null(await fixture.Store.GetFlightPriceAsync("BK-1001", "FL-000"));
    }

    /// <summary>
    /// The approval gate prices a rebooking from here. If this returned 180 for BK-1003,
    /// a flight belonging to BK-1001, the gate would clear a cross-booking rebooking under
    /// the 300 limit and no human would ever see it.
    /// </summary>
    [DockerRequiredFact]
    public async Task GetFlightPrice_FlightOfAnotherBooking_ReturnsNull()
    {
        Assert.Null(await fixture.Store.GetFlightPriceAsync("BK-1003", "FL-201"));
    }

    [DockerRequiredFact]
    public async Task GetHotelPrice_OptionOfThatBooking_ReturnsTheSeededPrice()
    {
        Assert.Equal(120, await fixture.Store.GetHotelPriceAsync("BK-1001", "HTL-BER"));
    }

    [DockerRequiredFact]
    public async Task GetHotelPrice_UnknownId_ReturnsNull()
    {
        Assert.Null(await fixture.Store.GetHotelPriceAsync("BK-1001", "HTL-000"));
    }

    [DockerRequiredFact]
    public async Task GetHotelPrice_HotelOfAnotherBooking_ReturnsNull()
    {
        Assert.Null(await fixture.Store.GetHotelPriceAsync("BK-1003", "HTL-BER"));
    }

    [DockerRequiredFact]
    public async Task ApplyRebooking_AlternativeOfThatBooking_SetsStatusAndFlight()
    {
        var scratch = await fixture.CreateScratchBookingAsync();

        await fixture.Store.ApplyRebookingAsync(scratch.BookingRef, scratch.FlightId);

        var booking = await fixture.Store.GetBookingAsync(scratch.BookingRef);
        Assert.Equal("rebooked", booking!.Status);
        Assert.Equal(scratch.FlightId, booking.RebookedFlightId);
    }

    [DockerRequiredFact]
    public async Task ApplyRebooking_UnknownRef_Throws()
    {
        await Assert.ThrowsAsync<InvalidOperationException>(
            () => fixture.Store.ApplyRebookingAsync("BK-0000", "FL-201"));
    }

    [DockerRequiredFact]
    public async Task ApplyRebooking_FlightOfAnotherBooking_ThrowsAndLeavesTheBookingAlone()
    {
        var scratch = await fixture.CreateScratchBookingAsync();

        await Assert.ThrowsAsync<InvalidOperationException>(
            () => fixture.Store.ApplyRebookingAsync(scratch.BookingRef, "FL-201"));

        var booking = await fixture.Store.GetBookingAsync(scratch.BookingRef);
        Assert.Equal("cancelled", booking!.Status);
        Assert.Null(booking.RebookedFlightId);
    }

    [DockerRequiredFact]
    public async Task AddHotel_OptionOfThatBooking_SetsTheHotel()
    {
        var scratch = await fixture.CreateScratchBookingAsync();

        await fixture.Store.AddHotelAsync(scratch.BookingRef, scratch.HotelId);

        var booking = await fixture.Store.GetBookingAsync(scratch.BookingRef);
        Assert.Equal(scratch.HotelId, booking!.HotelId);
    }

    [DockerRequiredFact]
    public async Task AddHotel_UnknownRef_Throws()
    {
        await Assert.ThrowsAsync<InvalidOperationException>(
            () => fixture.Store.AddHotelAsync("BK-0000", "HTL-BER"));
    }

    [DockerRequiredFact]
    public async Task AddHotel_HotelOfAnotherBooking_ThrowsAndLeavesTheBookingAlone()
    {
        var scratch = await fixture.CreateScratchBookingAsync();

        await Assert.ThrowsAsync<InvalidOperationException>(
            () => fixture.Store.AddHotelAsync(scratch.BookingRef, "HTL-BER"));

        var booking = await fixture.Store.GetBookingAsync(scratch.BookingRef);
        Assert.Null(booking!.HotelId);
    }
}
