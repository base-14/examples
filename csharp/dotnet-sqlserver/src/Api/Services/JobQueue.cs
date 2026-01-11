using System.Diagnostics;
using System.Text.Json;
using Api.Data;
using Api.Data.Entities;
using Api.Telemetry;
using Microsoft.EntityFrameworkCore;
using OpenTelemetry;
using OpenTelemetry.Context.Propagation;

namespace Api.Services;

public class JobQueue(AppDbContext context)
{
    private static readonly ActivitySource ActivitySource = new("DotnetSqlServer.JobQueue");
    private static readonly TextMapPropagator Propagator = Propagators.DefaultTextMapPropagator;

    public async Task EnqueueAsync(string kind, object payload)
    {
        using var activity = ActivitySource.StartActivity("job.enqueue");
        activity?.SetTag("job.kind", kind);

        var traceContext = new Dictionary<string, string>();
        Propagator.Inject(
            new PropagationContext(Activity.Current?.Context ?? default, Baggage.Current),
            traceContext,
            (dict, key, value) => dict[key] = value);

        var job = new Job
        {
            Kind = kind,
            Payload = JsonSerializer.Serialize(payload),
            TraceContext = JsonSerializer.Serialize(traceContext)
        };

        context.Jobs.Add(job);
        await context.SaveChangesAsync();

        activity?.SetTag("job.id", job.Id);
        AppMetrics.JobsEnqueued.Add(1);
    }

    public async Task<Job?> DequeueAsync()
    {
        await using var transaction = await context.Database.BeginTransactionAsync();

        try
        {
            var job = await context.Jobs
                .FromSqlRaw("""
                    SELECT TOP(1) * FROM Jobs WITH (UPDLOCK, READPAST)
                    WHERE (Status = 'pending')
                       OR (Status = 'retry' AND NextRetryAt <= GETUTCDATE())
                    ORDER BY CreatedAt
                    """)
                .FirstOrDefaultAsync();

            if (job is null)
            {
                await transaction.RollbackAsync();
                return null;
            }

            job.Status = "processing";
            job.ProcessedAt = DateTime.UtcNow;
            await context.SaveChangesAsync();
            await transaction.CommitAsync();

            return job;
        }
        catch
        {
            await transaction.RollbackAsync();
            throw;
        }
    }

    public async Task CompleteAsync(int jobId)
    {
        await context.Jobs
            .Where(j => j.Id == jobId)
            .ExecuteUpdateAsync(s => s.SetProperty(j => j.Status, "completed"));
        AppMetrics.JobsCompleted.Add(1);
    }

    public async Task FailAsync(int jobId, string error)
    {
        var job = await context.Jobs.FindAsync(jobId);
        if (job is null) return;

        job.RetryCount++;
        job.Error = error;

        if (job.RetryCount < job.MaxRetries)
        {
            var backoffSeconds = Math.Pow(2, job.RetryCount) * 10;
            job.Status = "retry";
            job.NextRetryAt = DateTime.UtcNow.AddSeconds(backoffSeconds);
        }
        else
        {
            job.Status = "failed";
            AppMetrics.JobsFailed.Add(1);
        }

        await context.SaveChangesAsync();
    }

    public static PropagationContext ExtractTraceContext(string? traceContextJson)
    {
        if (string.IsNullOrEmpty(traceContextJson))
            return default;

        try
        {
            var traceContext = JsonSerializer.Deserialize<Dictionary<string, string>>(traceContextJson) ?? [];
            return Propagator.Extract(default, traceContext, (dict, key) =>
                dict.TryGetValue(key, out var value) ? [value] : []);
        }
        catch
        {
            return default;
        }
    }
}
