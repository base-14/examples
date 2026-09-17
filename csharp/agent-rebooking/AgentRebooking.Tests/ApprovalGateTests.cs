using System.Text.Json;
using AgentRebooking.Runs;
using AgentRebooking.Tests.Support;
using Microsoft.Extensions.AI;

namespace AgentRebooking.Tests;

public class ApprovalGateTests
{
    private const int Limit = 300;

    private static FunctionCallContent Call(string name, params (string Key, object? Value)[] arguments) =>
        new("call-1", name, arguments.ToDictionary(a => a.Key, a => a.Value));

    [Fact]
    public async Task UnderLimitFlightIsAutoApproved()
    {
        var gate = new ApprovalGate(new SeedPriceLookup(), Limit);

        var decision = await gate.DecideAsync(
            Call("rebook", ("booking_ref", "BK-1001"), ("flight_id", "FL-201")));

        Assert.True(decision.AutoApprove);
        Assert.Equal(180, decision.Amount);
        Assert.Equal(Limit, decision.Limit);
    }

    [Fact]
    public async Task OverLimitFlightIsPendingWithItsAmount()
    {
        var gate = new ApprovalGate(new SeedPriceLookup(), Limit);

        var decision = await gate.DecideAsync(
            Call("rebook", ("booking_ref", "BK-1002"), ("flight_id", "FL-301")));

        Assert.False(decision.AutoApprove);
        Assert.Equal(620, decision.Amount);
        Assert.Equal(Limit, decision.Limit);
    }

    [Fact]
    public async Task UnknownFlightIdIsPendingWithNoAmount()
    {
        var gate = new ApprovalGate(new SeedPriceLookup(), Limit);

        var decision = await gate.DecideAsync(
            Call("rebook", ("booking_ref", "BK-1001"), ("flight_id", "FL-999")));

        Assert.False(decision.AutoApprove);
        Assert.Null(decision.Amount);
    }

    [Fact]
    public async Task MissingFlightIdArgumentIsPending()
    {
        var gate = new ApprovalGate(new SeedPriceLookup(), Limit);

        var decision = await gate.DecideAsync(Call("rebook", ("booking_ref", "BK-1001")));

        Assert.False(decision.AutoApprove);
        Assert.Null(decision.Amount);
    }

    [Fact]
    public async Task MissingBookingReferenceIsPending()
    {
        var gate = new ApprovalGate(new SeedPriceLookup(), Limit);

        var decision = await gate.DecideAsync(Call("rebook", ("flight_id", "FL-201")));

        Assert.False(decision.AutoApprove);
        Assert.Null(decision.Amount);
    }

    /// <summary>
    /// FL-201 is cheap, but it belongs to BK-1001. Priced against BK-1003 there is no such
    /// alternative, so the gate must hold the call for a human rather than let a price
    /// borrowed from another booking clear the limit.
    /// </summary>
    [Fact]
    public async Task FlightFromAnotherBookingIsPending()
    {
        var gate = new ApprovalGate(new SeedPriceLookup(), Limit);

        var decision = await gate.DecideAsync(
            Call("rebook", ("booking_ref", "BK-1003"), ("flight_id", "FL-201")));

        Assert.False(decision.AutoApprove);
        Assert.Null(decision.Amount);
    }

    [Fact]
    public async Task UnderLimitHotelIsAutoApproved()
    {
        var gate = new ApprovalGate(new SeedPriceLookup(), Limit);

        var decision = await gate.DecideAsync(
            Call("add_hotel", ("booking_ref", "BK-1001"), ("hotel_id", "HTL-BER")));

        Assert.True(decision.AutoApprove);
        Assert.Equal(120, decision.Amount);
    }

    [Fact]
    public async Task ToolTheGateDoesNotRecogniseIsPending()
    {
        var gate = new ApprovalGate(new SeedPriceLookup(), Limit);

        var decision = await gate.DecideAsync(Call("wire_transfer", ("amount", "1000000")));

        Assert.False(decision.AutoApprove);
        Assert.Null(decision.Amount);
    }

    /// <summary>
    /// A price the model writes into the call is ignored. The gate prices by id from the
    /// store, so an under-limit number in the arguments cannot buy an over-limit flight.
    /// </summary>
    [Fact]
    public async Task PriceSuppliedByTheModelIsIgnored()
    {
        var gate = new ApprovalGate(new SeedPriceLookup(), Limit);

        var decision = await gate.DecideAsync(
            Call("rebook", ("booking_ref", "BK-1002"), ("flight_id", "FL-301"), ("price", 1)));

        Assert.False(decision.AutoApprove);
        Assert.Equal(620, decision.Amount);
    }

    /// <summary>
    /// Tool arguments arriving from a model are deserialised as <see cref="JsonElement"/>,
    /// not as strings, so the gate has to read both shapes.
    /// </summary>
    [Fact]
    public async Task JsonElementArgumentsAreRead()
    {
        var gate = new ApprovalGate(new SeedPriceLookup(), Limit);
        var arguments = JsonSerializer.Deserialize<Dictionary<string, object?>>(
            """{"booking_ref":"BK-1001","flight_id":"FL-201"}""")!;

        var decision = await gate.DecideAsync(new FunctionCallContent("call-1", "rebook", arguments));

        Assert.True(decision.AutoApprove);
        Assert.Equal(180, decision.Amount);
    }
}

/// <summary>
/// The same decisions, priced through <see cref="BookingStorePriceLookup"/> against the
/// real schema and seed rows. These prove the production wiring reads Postgres; the
/// container-free tests above prove the decision logic.
/// </summary>
[Collection(PostgresCollection.Name)]
public class ApprovalGateStoreTests(PostgresFixture fixture)
{
    private const int Limit = 300;

    private static FunctionCallContent Call(string name, params (string Key, object? Value)[] arguments) =>
        new("call-1", name, arguments.ToDictionary(a => a.Key, a => a.Value));

    [DockerRequiredFact]
    public async Task UnderLimitFlightIsAutoApprovedFromPostgres()
    {
        var gate = new ApprovalGate(new BookingStorePriceLookup(fixture.Store), Limit);

        var decision = await gate.DecideAsync(
            Call("rebook", ("booking_ref", "BK-1001"), ("flight_id", "FL-201")));

        Assert.True(decision.AutoApprove);
        Assert.Equal(180, decision.Amount);
    }

    [DockerRequiredFact]
    public async Task OverLimitFlightIsPendingFromPostgres()
    {
        var gate = new ApprovalGate(new BookingStorePriceLookup(fixture.Store), Limit);

        var decision = await gate.DecideAsync(
            Call("rebook", ("booking_ref", "BK-1002"), ("flight_id", "FL-301")));

        Assert.False(decision.AutoApprove);
        Assert.Equal(620, decision.Amount);
    }

    [DockerRequiredFact]
    public async Task FlightFromAnotherBookingIsPendingFromPostgres()
    {
        var gate = new ApprovalGate(new BookingStorePriceLookup(fixture.Store), Limit);

        var decision = await gate.DecideAsync(
            Call("rebook", ("booking_ref", "BK-1003"), ("flight_id", "FL-201")));

        Assert.False(decision.AutoApprove);
        Assert.Null(decision.Amount);
    }

    [DockerRequiredFact]
    public async Task UnderLimitHotelIsAutoApprovedFromPostgres()
    {
        var gate = new ApprovalGate(new BookingStorePriceLookup(fixture.Store), Limit);

        var decision = await gate.DecideAsync(
            Call("add_hotel", ("booking_ref", "BK-1003"), ("hotel_id", "HTL-CDG")));

        Assert.True(decision.AutoApprove);
        Assert.Equal(140, decision.Amount);
    }
}
