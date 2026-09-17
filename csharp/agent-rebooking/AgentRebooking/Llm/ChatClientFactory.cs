using Anthropic;
using Anthropic.Core;
using Microsoft.Extensions.AI;
using OllamaSharp;
using OpenAI;
using OpenAI.Chat;

namespace AgentRebooking.Llm;

/// <summary>
/// The settings <see cref="ChatClientFactory.Create"/> needs to build a client for one
/// provider. Used for both the primary and, when set, the fallback provider.
/// </summary>
public sealed record ChatClientFactoryOptions(
    string Provider,
    string Model,
    string OllamaBaseUrl,
    string? OpenAiApiKey,
    string? AnthropicApiKey,
    bool AllowHostedProvider);

/// <summary>
/// Builds an <see cref="IChatClient"/> for the configured provider. Ollama runs on the
/// host with no remote call; OpenAI and Anthropic are hosted providers, gated by
/// <see cref="ChatClientFactoryOptions.AllowHostedProvider"/> so a stray exported API key
/// plus a mistyped provider cannot produce a paid call.
/// </summary>
public static class ChatClientFactory
{
    public static IChatClient Create(ChatClientFactoryOptions options)
    {
        var provider = options.Provider.Trim().ToLowerInvariant();

        if (provider != "ollama" && !options.AllowHostedProvider)
        {
            throw new InvalidOperationException(
                $"LLM_PROVIDER is '{options.Provider}', a hosted provider, but ALLOW_HOSTED_PROVIDER is not " +
                "'true'. Set ALLOW_HOSTED_PROVIDER=true to let the service start a hosted provider.");
        }

        return provider switch
        {
            "ollama" => new OllamaApiClient(new Uri(options.OllamaBaseUrl), options.Model),
            "openai" => new OpenAIClient(options.OpenAiApiKey ?? string.Empty)
                .GetChatClient(options.Model)
                .AsIChatClient(),
            "anthropic" => new AnthropicClient(new ClientOptions { ApiKey = options.AnthropicApiKey ?? string.Empty })
                .AsIChatClient(options.Model),
            _ => throw new InvalidOperationException(
                $"Unknown LLM_PROVIDER '{options.Provider}'. Supported values: ollama, openai, anthropic."),
        };
    }
}
