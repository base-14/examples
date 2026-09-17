using AgentRebooking.Llm;
using Microsoft.Extensions.AI;

namespace AgentRebooking.Tests;

/// <summary>
/// <see cref="Pricing"/> loaded from the repo's <c>_shared/pricing.json</c>, copied into
/// the test output as <c>pricing.json</c> so these tests never depend on
/// <c>/app/pricing.json</c> or the <c>PRICING_FILE</c> environment variable.
/// </summary>
public sealed class PricingTests
{
    private static string AssetPath => Path.Combine(AppContext.BaseDirectory, "pricing.json");

    [Fact]
    public void KnownModel_ComputesCostFromInputAndOutputRates()
    {
        var pricing = Pricing.LoadFromFile(AssetPath);
        var usage = new UsageDetails { InputTokenCount = 1_000_000, OutputTokenCount = 1_000_000 };

        // gpt-4.1-mini: input 0.4 USD/M, output 1.6 USD/M.
        Assert.Equal(2.0, pricing.CostFor("openai", "gpt-4.1-mini", usage), precision: 6);
    }

    [Fact]
    public void OllamaModel_HasNoEntry_ReturnsZero()
    {
        var pricing = Pricing.LoadFromFile(AssetPath);
        var usage = new UsageDetails { InputTokenCount = 12, OutputTokenCount = 5 };

        Assert.Equal(0d, pricing.CostFor("ollama", "qwen3.5:9b", usage));
    }

    [Fact]
    public void NullUsage_ReturnsZero()
    {
        var pricing = Pricing.LoadFromFile(AssetPath);

        Assert.Equal(0d, pricing.CostFor("openai", "gpt-4.1-mini", usage: null));
    }

    [Fact]
    public void MissingPricingFile_ReturnsZeroForEveryModel()
    {
        var pricing = Pricing.LoadFromFile("/nonexistent/pricing.json");
        var usage = new UsageDetails { InputTokenCount = 1_000_000, OutputTokenCount = 1_000_000 };

        Assert.Equal(0d, pricing.CostFor("openai", "gpt-4.1-mini", usage));
    }

    [Fact]
    public void PricingFileEnvVar_IsHonouredWhenSet()
    {
        var original = Environment.GetEnvironmentVariable("PRICING_FILE");
        Environment.SetEnvironmentVariable("PRICING_FILE", "/env/pricing.json");
        try
        {
            var pricing = Pricing.LoadFromFile();

            Assert.Equal("/env/pricing.json", pricing.ResolvedPath);
        }
        finally
        {
            Environment.SetEnvironmentVariable("PRICING_FILE", original);
        }
    }

    [Fact]
    public void PricingFileEnvVarUnset_DefaultsToAppPricingJson()
    {
        var original = Environment.GetEnvironmentVariable("PRICING_FILE");
        Environment.SetEnvironmentVariable("PRICING_FILE", null);
        try
        {
            var pricing = Pricing.LoadFromFile();

            Assert.Equal("/app/pricing.json", pricing.ResolvedPath);
        }
        finally
        {
            Environment.SetEnvironmentVariable("PRICING_FILE", original);
        }
    }
}
