using System.Text.RegularExpressions;
using AgentRebooking.Data;
using AgentRebooking.Tests.Support;

namespace AgentRebooking.Tests;

/// <summary>
/// Pins the in-test price table to <c>Data/Seed.sql</c>, the file the app applies at
/// startup and the test project copies into its output. The gate and run store tests price
/// through <see cref="SeedPriceLookup"/> so they need no container; without this, an edit
/// to the seed and not to the copy would only show up in the Postgres-backed tests.
/// </summary>
public class SeedPriceLookupTests
{
    private static readonly string Seed = File.ReadAllText(BookingStore.DefaultSeedPath);

    [Fact]
    public async Task EveryFlightInTheSeedIsPricedAndNothingElseIs()
    {
        var lookup = new SeedPriceLookup();
        var bookings = BookingRefs();
        var flights = Rows("flight_alternatives", columns: 3)
            .ToDictionary(row => (Booking: row[1], Flight: row[0]), row => int.Parse(row[2]));

        Assert.NotEmpty(flights);

        // Set equality first: everything below is queried from pairs the seed names, so a
        // pair the copy has invented would otherwise never be asked for.
        Assert.Equal(flights.Keys.ToHashSet(), SeedPriceLookup.FlightKeys.ToHashSet());

        foreach (var booking in bookings)
        {
            foreach (var flight in flights.Keys.Select(key => key.Flight).Distinct())
            {
                var expected = flights.TryGetValue((booking, flight), out var price) ? price : (int?)null;

                Assert.Equal(expected, await lookup.GetFlightPriceAsync(booking, flight));
            }
        }
    }

    [Fact]
    public async Task EveryHotelInTheSeedIsPricedAndNothingElseIs()
    {
        var lookup = new SeedPriceLookup();
        var bookings = BookingRefs();
        var hotels = Rows("hotel_options", columns: 4)
            .ToDictionary(row => (Booking: row[1], Hotel: row[0]), row => int.Parse(row[3]));

        Assert.NotEmpty(hotels);

        Assert.Equal(hotels.Keys.ToHashSet(), SeedPriceLookup.HotelKeys.ToHashSet());

        foreach (var booking in bookings)
        {
            foreach (var hotel in hotels.Keys.Select(key => key.Hotel).Distinct())
            {
                var expected = hotels.TryGetValue((booking, hotel), out var price) ? price : (int?)null;

                Assert.Equal(expected, await lookup.GetHotelPriceAsync(booking, hotel));
            }
        }
    }

    private static List<string> BookingRefs() => [.. Rows("bookings", columns: 4).Select(row => row[0])];

    /// <summary>
    /// The value tuples of one INSERT in the seed, each as its column values with the
    /// quotes stripped. The seed is hand-written SQL in a fixed shape, so a regex over the
    /// statement is enough and keeps this test free of a parser.
    /// </summary>
    private static List<string[]> Rows(string table, int columns)
    {
        var statement = Seed
            .Split(';')
            .Single(candidate => candidate.Contains($"INSERT INTO {table}", StringComparison.Ordinal));

        // From VALUES on, so the column list in the INSERT is not read as a row.
        var values = statement[statement.IndexOf("VALUES", StringComparison.Ordinal)..];
        var value = string.Join(@",\s*", Enumerable.Repeat(@"'?([^',]+?)'?", columns));

        return [.. Regex.Matches(values, $@"\(\s*{value}\s*\)")
            .Select(match => match.Groups.Cast<Group>().Skip(1).Select(group => group.Value.Trim()).ToArray())];
    }
}
