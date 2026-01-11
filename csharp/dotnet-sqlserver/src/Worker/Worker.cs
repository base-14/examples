using System.Diagnostics;
using Api.Services;
using OpenTelemetry;

namespace Worker;

public class JobProcessor(
    IServiceScopeFactory scopeFactory,
    ILogger<JobProcessor> logger,
    IConfiguration configuration) : BackgroundService
{
    private static readonly ActivitySource ActivitySource = new("DotnetSqlServer.Worker");
    private readonly int _pollingIntervalMs = configuration.GetValue("JobProcessor:PollingIntervalMs", 1000);

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        logger.LogInformation("Job processor starting with {PollingInterval}ms polling interval", _pollingIntervalMs);

        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                using var scope = scopeFactory.CreateScope();
                var jobQueue = scope.ServiceProvider.GetRequiredService<JobQueue>();

                var job = await jobQueue.DequeueAsync();

                if (job is not null)
                {
                    var parentContext = JobQueue.ExtractTraceContext(job.TraceContext);

                    // Restore baggage from propagation context
                    Baggage.Current = parentContext.Baggage;

                    using var activity = ActivitySource.StartActivity(
                        "job.process",
                        ActivityKind.Consumer,
                        parentContext.ActivityContext);

                    activity?.SetTag("job.id", job.Id);
                    activity?.SetTag("job.kind", job.Kind);

                    // Add baggage items as span tags for correlation
                    foreach (var item in Baggage.Current)
                    {
                        activity?.SetTag($"baggage.{item.Key}", item.Value);
                    }

                    // Build log scope with job context and baggage
                    var scopeState = new Dictionary<string, object>
                    {
                        ["job.id"] = job.Id,
                        ["job.kind"] = job.Kind,
                        ["job.retry_count"] = job.RetryCount
                    };
                    foreach (var item in Baggage.Current)
                    {
                        scopeState[$"baggage.{item.Key}"] = item.Value;
                    }

                    using var logScope = logger.BeginScope(scopeState);

                    try
                    {
                        logger.LogInformation("Processing job {JobId} of kind {Kind}", job.Id, job.Kind);

                        await ProcessJobAsync(job.Kind, job.Payload);

                        await jobQueue.CompleteAsync(job.Id);
                        logger.LogInformation("Job {JobId} completed successfully", job.Id);
                    }
                    catch (Exception ex)
                    {
                        logger.LogError(ex, "Job {JobId} failed", job.Id);
                        await jobQueue.FailAsync(job.Id, ex.Message);
                        activity?.SetStatus(ActivityStatusCode.Error, ex.Message);
                    }
                }
                else
                {
                    await Task.Delay(_pollingIntervalMs, stoppingToken);
                }
            }
            catch (Exception ex)
            {
                logger.LogError(ex, "Error in job processing loop");
                await Task.Delay(5000, stoppingToken);
            }
        }
    }

    private Task ProcessJobAsync(string kind, string payload)
    {
        return kind switch
        {
            "notification" => HandleNotificationAsync(payload),
            _ => HandleUnknownJobAsync(kind, payload)
        };
    }

    private Task HandleUnknownJobAsync(string kind, string payload)
    {
        logger.LogWarning("Unknown job kind '{Kind}' with payload: {Payload}", kind, payload);
        return Task.CompletedTask;
    }

    private Task HandleNotificationAsync(string payload)
    {
        logger.LogInformation("Processing notification: {Payload}", payload);
        return Task.Delay(100);
    }
}
