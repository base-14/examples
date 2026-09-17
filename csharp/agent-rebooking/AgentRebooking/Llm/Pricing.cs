using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;

namespace AgentRebooking.Llm;

/// <summary>
/// Cost table loaded from <c>_shared/pricing.json</c>. The Dockerfile copies that file
/// to <c>/app/pricing.json</c>; <see cref="LoadFromFile"/> reads the <c>PRICING_FILE</c>
/// environment variable and falls back to that path. A model with no entry, such as the
/// default Ollama model, costs zero -- that is the documented default, not an error.
/// </summary>
public sealed class Pricing
{
    private const string DefaultPath = "/app/pricing.json";

    private readonly IReadOnlyDictionary<string, ModelRate> _rates;

    private Pricing(string resolvedPath, IReadOnlyDictionary<string, ModelRate> rates)
    {
        ResolvedPath = resolvedPath;
        _rates = rates;
    }

    /// <summary>
    /// The path <see cref="LoadFromFile"/> resolved and read from, or attempted to read
    /// from. Exposed so tests can assert which path was chosen without needing a real
    /// file at <c>/app/pricing.json</c>.
    /// </summary>
    public string ResolvedPath { get; }

    public static Pricing LoadFromFile(string? explicitPath = null)
    {
        var path = explicitPath
            ?? Environment.GetEnvironmentVariable("PRICING_FILE")
            ?? DefaultPath;

        if (!File.Exists(path))
        {
            return new Pricing(path, new Dictionary<string, ModelRate>());
        }

        using var stream = File.OpenRead(path);
        var document = JsonSerializer.Deserialize<PricingDocument>(stream);
        return new Pricing(path, document?.Models ?? new Dictionary<string, ModelRate>());
    }

    /// <summary>
    /// Cost in USD for one call. Looked up by model id; a model absent from the table,
    /// such as an Ollama tag, costs zero.
    /// </summary>
    public double CostFor(string provider, string model, UsageDetails? usage)
    {
        _ = provider;

        if (usage is null || !_rates.TryGetValue(model, out var rate))
        {
            return 0d;
        }

        var inputTokens = usage.InputTokenCount ?? 0;
        var outputTokens = usage.OutputTokenCount ?? 0;

        return (inputTokens / 1_000_000d * rate.Input) + (outputTokens / 1_000_000d * rate.Output);
    }

    private sealed record PricingDocument
    {
        [JsonPropertyName("models")]
        public Dictionary<string, ModelRate>? Models { get; init; }
    }

    private sealed record ModelRate
    {
        [JsonPropertyName("provider")]
        public string Provider { get; init; } = "";

        [JsonPropertyName("input")]
        public double Input { get; init; }

        [JsonPropertyName("output")]
        public double Output { get; init; }

        [JsonPropertyName("cached_input")]
        public double? CachedInput { get; init; }
    }
}
