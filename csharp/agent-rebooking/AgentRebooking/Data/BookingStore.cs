using Npgsql;

namespace AgentRebooking.Data;

public sealed record Booking(
    string BookingRef,
    string Origin,
    string Destination,
    DateOnly TravelDate,
    string Status,
    string? RebookedFlightId,
    string? HotelId)
{
    public string Route => $"{Origin}-{Destination}";
}

public sealed record FlightAlternative(string FlightId, int Price);

public sealed record HotelOption(string HotelId, string City, int Price);

public sealed record Alternatives(IReadOnlyList<FlightAlternative> Flights, HotelOption? Hotel);

/// <summary>
/// Reads and writes booking data on Postgres through Npgsql. Flight and hotel price
/// lookups are their own methods because the approval gate Task 6 adds reads a price
/// from here directly, server-side, rather than trusting a price the model supplies.
/// </summary>
public sealed class BookingStore : IAsyncDisposable
{
    private readonly NpgsqlDataSource _dataSource;

    private BookingStore(NpgsqlDataSource dataSource)
    {
        _dataSource = dataSource;
    }

    public static string DefaultSchemaPath => Path.Combine(AppContext.BaseDirectory, "Data", "Schema.sql");

    public static string DefaultSeedPath => Path.Combine(AppContext.BaseDirectory, "Data", "Seed.sql");

    public static BookingStore Create(string connectionString) => new(NpgsqlDataSource.Create(connectionString));

    /// <summary>
    /// Applies the schema then the seed rows. Both files are idempotent, so this is safe
    /// to run on every startup against a volume that already has the tables and rows, and
    /// it never resets a booking a previous run already rebooked. The flip side is that
    /// editing a seed value has no effect until the volume is removed; see `make reset`.
    /// </summary>
    public async Task ApplySchemaAndSeedAsync(
        string? schemaPath = null, string? seedPath = null, CancellationToken cancellationToken = default)
    {
        await using var connection = await _dataSource.OpenConnectionAsync(cancellationToken);
        await RunScriptAsync(connection, schemaPath ?? DefaultSchemaPath, cancellationToken);
        await RunScriptAsync(connection, seedPath ?? DefaultSeedPath, cancellationToken);
    }

    public async Task<Booking?> GetBookingAsync(string bookingRef, CancellationToken cancellationToken = default)
    {
        await using var connection = await _dataSource.OpenConnectionAsync(cancellationToken);
        await using var command = new NpgsqlCommand(
            """
            SELECT booking_ref, origin, destination, travel_date, status, rebooked_flight_id, hotel_id
            FROM bookings
            WHERE booking_ref = @booking_ref
            """,
            connection);
        command.Parameters.AddWithValue("booking_ref", bookingRef);

        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken))
        {
            return null;
        }

        return new Booking(
            BookingRef: reader.GetString(0),
            Origin: reader.GetString(1),
            Destination: reader.GetString(2),
            TravelDate: reader.GetFieldValue<DateOnly>(3),
            Status: reader.GetString(4),
            RebookedFlightId: reader.IsDBNull(5) ? null : reader.GetString(5),
            HotelId: reader.IsDBNull(6) ? null : reader.GetString(6));
    }

    public async Task<Alternatives> ListAlternativesAsync(
        string bookingRef, CancellationToken cancellationToken = default)
    {
        await using var connection = await _dataSource.OpenConnectionAsync(cancellationToken);

        var flights = new List<FlightAlternative>();
        await using (var command = new NpgsqlCommand(
            "SELECT flight_id, price FROM flight_alternatives WHERE booking_ref = @booking_ref ORDER BY price",
            connection))
        {
            command.Parameters.AddWithValue("booking_ref", bookingRef);
            await using var reader = await command.ExecuteReaderAsync(cancellationToken);
            while (await reader.ReadAsync(cancellationToken))
            {
                flights.Add(new FlightAlternative(reader.GetString(0), reader.GetInt32(1)));
            }
        }

        HotelOption? hotel = null;
        await using (var command = new NpgsqlCommand(
            "SELECT hotel_id, city, price FROM hotel_options WHERE booking_ref = @booking_ref ORDER BY hotel_id LIMIT 1",
            connection))
        {
            command.Parameters.AddWithValue("booking_ref", bookingRef);
            await using var reader = await command.ExecuteReaderAsync(cancellationToken);
            if (await reader.ReadAsync(cancellationToken))
            {
                hotel = new HotelOption(reader.GetString(0), reader.GetString(1), reader.GetInt32(2));
            }
        }

        return new Alternatives(flights, hotel);
    }

    /// <summary>
    /// The price of a flight offered for this booking, or null when the flight is not one
    /// of that booking's alternatives. Scoped to the booking on purpose: the approval gate
    /// compares this price against the limit, so an unscoped lookup would let a cheap
    /// flight from a different booking clear the limit and skip the human.
    /// </summary>
    public async Task<int?> GetFlightPriceAsync(
        string bookingRef, string flightId, CancellationToken cancellationToken = default)
    {
        await using var connection = await _dataSource.OpenConnectionAsync(cancellationToken);
        await using var command = new NpgsqlCommand(
            """
            SELECT price FROM flight_alternatives
            WHERE booking_ref = @booking_ref AND flight_id = @flight_id
            """,
            connection);
        command.Parameters.AddWithValue("booking_ref", bookingRef);
        command.Parameters.AddWithValue("flight_id", flightId);

        var result = await command.ExecuteScalarAsync(cancellationToken);
        return result is int price ? price : null;
    }

    /// <summary>
    /// The price of a hotel offered for this booking, or null when the hotel is not that
    /// booking's option. Scoped for the same reason as <see cref="GetFlightPriceAsync"/>.
    /// </summary>
    public async Task<int?> GetHotelPriceAsync(
        string bookingRef, string hotelId, CancellationToken cancellationToken = default)
    {
        await using var connection = await _dataSource.OpenConnectionAsync(cancellationToken);
        await using var command = new NpgsqlCommand(
            """
            SELECT price FROM hotel_options
            WHERE booking_ref = @booking_ref AND hotel_id = @hotel_id
            """,
            connection);
        command.Parameters.AddWithValue("booking_ref", bookingRef);
        command.Parameters.AddWithValue("hotel_id", hotelId);

        var result = await command.ExecuteScalarAsync(cancellationToken);
        return result is int price ? price : null;
    }

    public async Task ApplyRebookingAsync(
        string bookingRef, string flightId, CancellationToken cancellationToken = default)
    {
        await using var connection = await _dataSource.OpenConnectionAsync(cancellationToken);
        await using var command = new NpgsqlCommand(
            """
            UPDATE bookings SET status = 'rebooked', rebooked_flight_id = @flight_id
            WHERE booking_ref = @booking_ref
              AND EXISTS (
                  SELECT 1 FROM flight_alternatives
                  WHERE booking_ref = @booking_ref AND flight_id = @flight_id)
            """,
            connection);
        command.Parameters.AddWithValue("flight_id", flightId);
        command.Parameters.AddWithValue("booking_ref", bookingRef);

        var rows = await command.ExecuteNonQueryAsync(cancellationToken);
        if (rows == 0)
        {
            throw new InvalidOperationException(
                $"Booking '{bookingRef}' has no alternative flight '{flightId}'.");
        }
    }

    public async Task AddHotelAsync(
        string bookingRef, string hotelId, CancellationToken cancellationToken = default)
    {
        await using var connection = await _dataSource.OpenConnectionAsync(cancellationToken);
        await using var command = new NpgsqlCommand(
            """
            UPDATE bookings SET hotel_id = @hotel_id
            WHERE booking_ref = @booking_ref
              AND EXISTS (
                  SELECT 1 FROM hotel_options
                  WHERE booking_ref = @booking_ref AND hotel_id = @hotel_id)
            """,
            connection);
        command.Parameters.AddWithValue("hotel_id", hotelId);
        command.Parameters.AddWithValue("booking_ref", bookingRef);

        var rows = await command.ExecuteNonQueryAsync(cancellationToken);
        if (rows == 0)
        {
            throw new InvalidOperationException(
                $"Booking '{bookingRef}' has no hotel option '{hotelId}'.");
        }
    }

    public ValueTask DisposeAsync() => _dataSource.DisposeAsync();

    private static async Task RunScriptAsync(
        NpgsqlConnection connection, string path, CancellationToken cancellationToken)
    {
        var sql = await File.ReadAllTextAsync(path, cancellationToken);
        await using var command = new NpgsqlCommand(sql, connection);
        await command.ExecuteNonQueryAsync(cancellationToken);
    }
}
