using AgentRebooking.Llm;

namespace AgentRebooking.Tests;

/// <summary>
/// The hosted provider guard: <see cref="ChatClientFactory.Create"/> refuses to build a
/// hosted provider client unless <c>ALLOW_HOSTED_PROVIDER</c> is explicitly true. Keys
/// used here are hardcoded dummy strings, never read from the environment, and
/// construction never calls out to a provider -- only an actual chat call would.
/// </summary>
public sealed class ChatClientFactoryTests
{
    private const string DummyKey = "unit-test-not-a-real-key";

    [Fact]
    public void HostedProvider_WithoutAllowFlag_ThrowsAndNamesTheFlag()
    {
        var options = new ChatClientFactoryOptions(
            Provider: "openai",
            Model: "gpt-4.1-mini",
            OllamaBaseUrl: "http://localhost:11434",
            OpenAiApiKey: DummyKey,
            AnthropicApiKey: null,
            AllowHostedProvider: false);

        var ex = Assert.Throws<InvalidOperationException>(
            () => ChatClientFactory.Create(options));

        Assert.Contains("ALLOW_HOSTED_PROVIDER", ex.Message);
    }

    // Named for exactly what this proves: construction succeeds and returns a client.
    // It does not prove no outbound request happens -- doing that deterministically
    // would mean giving ChatClientFactory an injectable HttpClient/transport so a test
    // can assert zero requests on a fake handler, which is a bigger change than this
    // fix round covers. The OpenAI/Anthropic SDKs are lazy (no I/O until a chat call
    // is made), so no call happens today, but this test does not verify that itself.
    [Fact]
    public void HostedProvider_WithAllowFlagTrue_ConstructsClientSuccessfully()
    {
        var options = new ChatClientFactoryOptions(
            Provider: "openai",
            Model: "gpt-4.1-mini",
            OllamaBaseUrl: "http://localhost:11434",
            OpenAiApiKey: DummyKey,
            AnthropicApiKey: null,
            AllowHostedProvider: true);

        using var client = ChatClientFactory.Create(options);

        Assert.NotNull(client);
    }

    [Fact]
    public void AnthropicPrereleasePackage_WithAllowFlagTrue_ConstructsClient()
    {
        var options = new ChatClientFactoryOptions(
            Provider: "anthropic",
            Model: "claude-sonnet-5",
            OllamaBaseUrl: "http://localhost:11434",
            OpenAiApiKey: null,
            AnthropicApiKey: DummyKey,
            AllowHostedProvider: true);

        using var client = ChatClientFactory.Create(options);

        Assert.NotNull(client);
    }

    [Fact]
    public void OllamaProvider_NeverGatedByAllowFlag()
    {
        var options = new ChatClientFactoryOptions(
            Provider: "ollama",
            Model: "qwen3.5:9b",
            OllamaBaseUrl: "http://localhost:11434",
            OpenAiApiKey: null,
            AnthropicApiKey: null,
            AllowHostedProvider: false);

        using var client = ChatClientFactory.Create(options);

        Assert.NotNull(client);
    }

    [Fact]
    public void UnknownProvider_WithoutAllowFlag_FailsOnTheGuardNotTheProviderName()
    {
        var options = new ChatClientFactoryOptions(
            Provider: "google",
            Model: "gemini-3.6-flash",
            OllamaBaseUrl: "http://localhost:11434",
            OpenAiApiKey: null,
            AnthropicApiKey: null,
            AllowHostedProvider: false);

        var ex = Assert.Throws<InvalidOperationException>(
            () => ChatClientFactory.Create(options));

        Assert.Contains("ALLOW_HOSTED_PROVIDER", ex.Message);
    }

    [Fact]
    public void UnknownProvider_WithAllowFlagTrue_ThrowsUnknownProvider()
    {
        var options = new ChatClientFactoryOptions(
            Provider: "google",
            Model: "gemini-3.6-flash",
            OllamaBaseUrl: "http://localhost:11434",
            OpenAiApiKey: null,
            AnthropicApiKey: null,
            AllowHostedProvider: true);

        var ex = Assert.Throws<InvalidOperationException>(
            () => ChatClientFactory.Create(options));

        Assert.Contains("Unknown LLM_PROVIDER", ex.Message);
    }
}
