using Microsoft.Data.SqlClient;

namespace HelloSqlServer;

public sealed class GreetingStore(string connectionString)
{
    private const int StartupAttempts = 15;
    private static readonly TimeSpan StartupRetryDelay = TimeSpan.FromSeconds(3);

    public async Task EnsureSchemaAsync(CancellationToken ct)
    {
        var builder = new SqlConnectionStringBuilder(connectionString);
        var databaseName = builder.InitialCatalog;
        builder.InitialCatalog = "master";

        for (var attempt = 1; ; attempt++)
        {
            try
            {
                await using (var master = new SqlConnection(builder.ConnectionString))
                {
                    await master.OpenAsync(ct);
                    await using var createDb = master.CreateCommand();
                    createDb.CommandText =
                        $"IF DB_ID(N'{databaseName}') IS NULL CREATE DATABASE [{databaseName}]";
                    await createDb.ExecuteNonQueryAsync(ct);
                }

                await using var connection = new SqlConnection(connectionString);
                await connection.OpenAsync(ct);
                await using var createTable = connection.CreateCommand();
                createTable.CommandText = """
                    IF OBJECT_ID(N'dbo.Greetings', N'U') IS NULL
                    CREATE TABLE dbo.Greetings (
                        Id INT IDENTITY(1,1) PRIMARY KEY,
                        Name NVARCHAR(100) NOT NULL,
                        GreetedAt DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
                    )
                    """;
                await createTable.ExecuteNonQueryAsync(ct);
                return;
            }
            catch (SqlException) when (attempt < StartupAttempts)
            {
                await Task.Delay(StartupRetryDelay, ct);
            }
        }
    }

    public async Task PingAsync(CancellationToken ct)
    {
        await using var connection = new SqlConnection(connectionString);
        await connection.OpenAsync(ct);
        await using var command = connection.CreateCommand();
        command.CommandText = "SELECT 1";
        await command.ExecuteScalarAsync(ct);
    }

    public async Task<int> RecordGreetingAsync(string name, CancellationToken ct)
    {
        await using var connection = new SqlConnection(connectionString);
        await connection.OpenAsync(ct);

        await using (var insert = connection.CreateCommand())
        {
            insert.CommandText = "INSERT INTO dbo.Greetings (Name) VALUES (@name)";
            insert.Parameters.AddWithValue("@name", name);
            await insert.ExecuteNonQueryAsync(ct);
        }

        await using var count = connection.CreateCommand();
        count.CommandText = "SELECT COUNT(*) FROM dbo.Greetings";
        return (int)(await count.ExecuteScalarAsync(ct))!;
    }
}
