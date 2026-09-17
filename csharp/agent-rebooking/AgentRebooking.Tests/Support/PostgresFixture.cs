using AgentRebooking.Data;
using Npgsql;
using Testcontainers.PostgreSql;

namespace AgentRebooking.Tests.Support;

/// <summary>
/// A booking seeded for one test, with its own flight and hotel, so write tests never
/// mutate the three shared bookings the read tests assert against.
/// </summary>
public sealed record ScratchBooking(string BookingRef, string FlightId, string HotelId);

/// <summary>
/// A real Postgres 18 via Testcontainers, schema and seed applied, shared across every
/// test class in <see cref="PostgresCollection"/> so one container serves the whole run.
/// When Docker is unreachable, <see cref="InitializeAsync"/> checks the same
/// <see cref="DockerProbe"/> the <see cref="DockerRequiredFactAttribute"/>-marked tests
/// already skipped on and does nothing, so fixture setup never throws on a machine with
/// no daemon.
/// </summary>
public sealed class PostgresFixture : IAsyncLifetime
{
    private PostgreSqlContainer? _container;
    private BookingStore? _store;

    public BookingStore Store => _store ?? throw NotInitialised();

    private string ConnectionString =>
        _container?.GetConnectionString() ?? throw NotInitialised();

    public async Task InitializeAsync()
    {
        if (!DockerProbe.IsAvailable)
        {
            return;
        }

        _container = new PostgreSqlBuilder("postgres:18-alpine")
            .WithDatabase("agentrebooking")
            .WithUsername("postgres")
            .WithPassword("postgres")
            .Build();
        await _container.StartAsync();

        _store = BookingStore.Create(_container.GetConnectionString());
        await _store.ApplySchemaAndSeedAsync();
    }

    /// <summary>
    /// Inserts a booking with one alternative flight and one hotel, under unique ids, and
    /// returns them. The flight is priced under the 300 limit and the hotel below it too.
    /// </summary>
    public async Task<ScratchBooking> CreateScratchBookingAsync()
    {
        var suffix = Guid.NewGuid().ToString("N")[..8].ToUpperInvariant();
        var scratch = new ScratchBooking($"BK-T{suffix}", $"FL-T{suffix}", $"HTL-T{suffix}");

        await using var connection = new NpgsqlConnection(ConnectionString);
        await connection.OpenAsync();
        await using var command = new NpgsqlCommand(
            """
            INSERT INTO bookings (booking_ref, origin, destination, travel_date)
            VALUES (@booking_ref, 'LHR', 'BER', '2026-10-02');

            INSERT INTO flight_alternatives (flight_id, booking_ref, price)
            VALUES (@flight_id, @booking_ref, 150);

            INSERT INTO hotel_options (hotel_id, booking_ref, city, price)
            VALUES (@hotel_id, @booking_ref, 'Berlin', 110);
            """,
            connection);
        command.Parameters.AddWithValue("booking_ref", scratch.BookingRef);
        command.Parameters.AddWithValue("flight_id", scratch.FlightId);
        command.Parameters.AddWithValue("hotel_id", scratch.HotelId);
        await command.ExecuteNonQueryAsync();

        return scratch;
    }

    public async Task DisposeAsync()
    {
        if (_store is not null)
        {
            await _store.DisposeAsync();
        }

        if (_container is not null)
        {
            await _container.DisposeAsync();
        }
    }

    private static InvalidOperationException NotInitialised() =>
        new("The Postgres fixture is not initialised because Docker was unavailable. "
            + "Tests needing it carry [DockerRequiredFact] and should have skipped.");
}

/// <summary>
/// Shares one <see cref="PostgresFixture"/>, and so one container, across every test
/// class that joins this collection.
/// </summary>
[CollectionDefinition(Name)]
public sealed class PostgresCollection : ICollectionFixture<PostgresFixture>
{
    public const string Name = "postgres";
}
