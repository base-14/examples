using System.Diagnostics;
using System.Diagnostics.Metrics;
using AgentRebooking.Agents;
using AgentRebooking.Api;
using AgentRebooking.Data;
using AgentRebooking.Llm;
using AgentRebooking.Runs;
using AgentRebooking.Telemetry;
using Microsoft.Extensions.AI;
using OpenTelemetry;
using OpenTelemetry.Logs;
using OpenTelemetry.Metrics;
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;

var builder = WebApplication.CreateBuilder(args);

var options = AgentRebookingOptions.FromConfiguration(builder.Configuration);
builder.Services.AddSingleton(options);

builder.Services.AddSingleton(sp =>
    BookingStore.Create(sp.GetRequiredService<AgentRebookingOptions>().PostgresConnectionString));

// Named exactly Sources.AgentRebooking, which TelemetryRegistration registers -- AddMeter matches
// by name, not by instance, but the two still have to agree or the four base14.gen_ai.*
// counters the gateway emits and the two base14.agent.approval.* ones are silently dropped.
builder.Services.AddSingleton(new Meter(Sources.AgentRebooking));
builder.Services.AddSingleton(sp => new ApprovalTelemetry(sp.GetRequiredService<Meter>()));

// Built once, eagerly, right after the app is built below: a hosted LLM_PROVIDER
// without ALLOW_HOSTED_PROVIDER=true must fail startup, not wait for the first
// request. Both agents take a dependency on this one client rather than building
// their own.
builder.Services.AddSingleton<IChatClient>(sp =>
{
    var opts = sp.GetRequiredService<AgentRebookingOptions>();

    var primary = ChatClientFactory.Create(new ChatClientFactoryOptions(
        opts.LlmProvider, opts.LlmModel, opts.OllamaBaseUrl,
        opts.OpenAiApiKey, opts.AnthropicApiKey, opts.AllowHostedProvider));
    var primaryInfo = new GatewayProvider(opts.LlmProvider, opts.LlmModel);

    IChatClient? fallback = null;
    GatewayProvider? fallbackInfo = null;
    if (opts.LlmFallbackProvider is not null)
    {
        fallback = ChatClientFactory.Create(new ChatClientFactoryOptions(
            opts.LlmFallbackProvider, opts.LlmModel, opts.OllamaBaseUrl,
            opts.OpenAiApiKey, opts.AnthropicApiKey, opts.AllowHostedProvider));
        fallbackInfo = new GatewayProvider(opts.LlmFallbackProvider, opts.LlmModel);
    }

    return new GatewayChatClient(
        primary, primaryInfo, fallback, fallbackInfo,
        Pricing.LoadFromFile(),
        sp.GetRequiredService<Meter>(),
        sp.GetRequiredService<ILoggerFactory>().CreateLogger<GatewayChatClient>());
});

var environment = builder.Configuration["SCOUT_ENVIRONMENT"]
    ?? builder.Environment.EnvironmentName.ToLowerInvariant();

builder.Logging.AddOpenTelemetry(logging =>
{
    logging.IncludeFormattedMessage = true;
    logging.IncludeScopes = true;
    logging.ParseStateValues = true;
});

// Stamps TraceId/SpanId onto every log record so logs correlate with traces.
builder.Logging.Configure(loggingOptions =>
{
    loggingOptions.ActivityTrackingOptions =
        ActivityTrackingOptions.TraceId
        | ActivityTrackingOptions.SpanId
        | ActivityTrackingOptions.ParentId;
});

builder.Services.AddOpenTelemetry()
    .ConfigureResource(resource => resource
        .AddAttributes(new[]
        {
            new KeyValuePair<string, object>("deployment.environment", environment),
            new KeyValuePair<string, object>("environment", environment),
            new KeyValuePair<string, object>("service.namespace", "examples"),
        }))
    // Both delegate to TelemetryRegistration, which TelemetryTests calls too: one place
    // wires Sources.TraceSourceNames and Sources.MeterNames into a provider, so a test can
    // build a bare provider the same way and prove it actually listens.
    .WithMetrics(metrics => TelemetryRegistration.ConfigureMetrics(metrics))
    .WithTracing(tracing => TelemetryRegistration.ConfigureTracing(tracing));

// Registered after AddOpenTelemetry on purpose. Hosted services start in registration
// order, and the MCP session has to open after the tracer provider has registered its
// listeners, or its startup spans and its trace context go missing. See AgentToolProvider.
builder.Services.AddSingleton<AgentToolProvider>();
builder.Services.AddHostedService(sp => sp.GetRequiredService<AgentToolProvider>());

builder.Services.AddSingleton(sp => new RunStore(
    // A fresh workflow per run: the executors the handoff builder creates carry that run's
    // state, so one shared instance would leak conversation between travellers.
    () => AgentSetup.BuildWorkflow(
        sp.GetRequiredService<IChatClient>(),
        sp.GetRequiredService<AgentToolProvider>().Tools,
        options.CaptureMessageContent),
    new ApprovalGate(
        new BookingStorePriceLookup(sp.GetRequiredService<BookingStore>()),
        options.ApprovalLimit),
    new RunStoreOptions(
        options.ApprovalTimeoutSeconds,
        options.RunTimeoutSeconds,
        options.RunTtlSeconds),
    sp.GetRequiredService<ApprovalTelemetry>(),
    TimeProvider.System,
    sp.GetRequiredService<ILogger<RunStore>>()));

builder.Services.AddHostedService<RunSweeper>();

// Skip OTLP if no endpoint is set; avoids connection-refused spam when running
// standalone outside Compose.
var useOtlpExporter = !string.IsNullOrWhiteSpace(
    builder.Configuration["OTEL_EXPORTER_OTLP_ENDPOINT"]);

if (useOtlpExporter)
{
    builder.Services.AddOpenTelemetry().UseOtlpExporter();
}

var app = builder.Build();

// Forces the IChatClient factory above to run now instead of on the first run: a
// misconfigured hosted provider throws here and the service never starts.
app.Services.GetRequiredService<IChatClient>();
app.Logger.LogInformation("Active LLM provider: {Provider} ({Model})", options.LlmProvider, options.LlmModel);

await app.Services.GetRequiredService<BookingStore>().ApplySchemaAndSeedAsync();

app.MapGet("/health", () => Results.Ok(new { status = "healthy" }));

app.MapRunEndpoints();

app.Run();

/// <summary>
/// Configuration bound once at startup from the flat environment-variable names the
/// design lists, so nothing downstream re-reads IConfiguration.
/// </summary>
internal sealed record AgentRebookingOptions(
    string LlmProvider,
    string LlmModel,
    string? LlmFallbackProvider,
    string OllamaBaseUrl,
    string? OpenAiApiKey,
    string? AnthropicApiKey,
    string PostgresConnectionString,
    int ApprovalLimit,
    int ApprovalTimeoutSeconds,
    int RunTimeoutSeconds,
    int RunTtlSeconds,
    bool CaptureMessageContent,
    bool AllowHostedProvider)
{
    public static AgentRebookingOptions FromConfiguration(IConfiguration configuration) => new(
        LlmProvider: configuration["LLM_PROVIDER"] ?? "ollama",
        LlmModel: configuration["LLM_MODEL"] ?? "qwen3.5:9b",
        LlmFallbackProvider: string.IsNullOrWhiteSpace(configuration["LLM_FALLBACK_PROVIDER"])
            ? null
            : configuration["LLM_FALLBACK_PROVIDER"],
        OllamaBaseUrl: configuration["OLLAMA_BASE_URL"] ?? "http://localhost:11434",
        OpenAiApiKey: configuration["OPENAI_API_KEY"],
        AnthropicApiKey: configuration["ANTHROPIC_API_KEY"],
        PostgresConnectionString: configuration["POSTGRES_CONNECTION_STRING"]
            ?? "Host=localhost;Port=5433;Database=agentrebooking;Username=postgres;Password=postgres",
        ApprovalLimit: int.Parse(configuration["APPROVAL_LIMIT"] ?? "300"),
        ApprovalTimeoutSeconds: int.Parse(configuration["APPROVAL_TIMEOUT_SECONDS"] ?? "600"),
        RunTimeoutSeconds: int.Parse(configuration["RUN_TIMEOUT_SECONDS"] ?? "300"),
        RunTtlSeconds: int.Parse(configuration["RUN_TTL_SECONDS"] ?? "3600"),
        CaptureMessageContent: ParseBoolLenient(configuration["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"]),
        // The service refuses to start a hosted provider (LLM_PROVIDER other than
        // ollama) unless this is explicitly true. See Llm/ChatClientFactory.cs.
        AllowHostedProvider: ParseBoolLenient(configuration["ALLOW_HOSTED_PROVIDER"]));

    // bool.Parse throws on a set-but-empty value, "1" or "yes". Fail closed instead:
    // anything that is not a case-insensitive "true" is false.
    private static bool ParseBoolLenient(string? value) =>
        string.Equals(value, "true", StringComparison.OrdinalIgnoreCase);
}

public partial class Program { }
