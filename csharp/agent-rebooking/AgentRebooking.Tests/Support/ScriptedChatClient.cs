using System.Runtime.CompilerServices;
using Microsoft.Extensions.AI;

namespace AgentRebooking.Tests.Support;

/// <summary>
/// An in-process <see cref="IChatClient"/> that plays back a fixed script of responses
/// and exceptions. Stands in for a real provider so gateway tests never call a hosted
/// LLM.
/// </summary>
internal sealed class ScriptedChatClient : IChatClient
{
    private readonly Queue<Func<ChatResponse>> _script;

    public ScriptedChatClient(IEnumerable<Func<ChatResponse>> script)
    {
        _script = new Queue<Func<ChatResponse>>(script);
    }

    public int CallCount { get; private set; }

    public static Func<ChatResponse> Fails(Exception exception) => () => throw exception;

    public static Func<ChatResponse> Succeeds(
        string text, string model, string responseId, int inputTokens, int outputTokens) =>
        () => new ChatResponse(new ChatMessage(ChatRole.Assistant, text))
        {
            ModelId = model,
            ResponseId = responseId,
            FinishReason = ChatFinishReason.Stop,
            Usage = new UsageDetails
            {
                InputTokenCount = inputTokens,
                OutputTokenCount = outputTokens,
            },
        };

    public Task<ChatResponse> GetResponseAsync(
        IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
    {
        CallCount++;

        if (_script.Count == 0)
        {
            throw new InvalidOperationException("ScriptedChatClient ran out of scripted responses.");
        }

        return Task.FromResult(_script.Dequeue()());
    }

    /// <summary>
    /// Plays the same script back as a stream: one update per response, and a scripted
    /// failure thrown from inside the enumeration rather than from the call that opens it.
    /// That is where a real provider outage surfaces, and it is the only place a caller can
    /// catch it.
    /// </summary>
    public async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        await Task.Yield();

        CallCount++;

        if (_script.Count == 0)
        {
            throw new InvalidOperationException("ScriptedChatClient ran out of scripted responses.");
        }

        var response = _script.Dequeue()();

        foreach (var message in response.Messages)
        {
            yield return new ChatResponseUpdate(message.Role, message.Contents);
        }
    }

    public object? GetService(Type serviceType, object? serviceKey = null) => null;

    public void Dispose()
    {
    }
}

/// <summary>
/// Throws from the call that opens the stream rather than from the first update. Every client
/// in this example is a compiler-generated iterator, which defers its work to the first
/// <c>MoveNextAsync</c>, so nothing in the live path fails this early. A client that validated
/// its arguments up front would, and the gateway counts that as a provider failure too.
/// </summary>
internal sealed class FailingToOpenChatClient(Exception failure) : IChatClient
{
    public Task<ChatResponse> GetResponseAsync(
        IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default) =>
        throw new NotSupportedException("This client exists for the streaming path only.");

    public IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
        IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default) =>
        throw failure;

    public object? GetService(Type serviceType, object? serviceKey = null) => null;

    public void Dispose()
    {
    }
}

/// <summary>
/// Cancels its own caller's token from inside the stream and then observes it, which is what
/// a run being timed out or shut down looks like from the gateway's point of view.
/// </summary>
internal sealed class CancellingChatClient(CancellationTokenSource cancellation) : IChatClient
{
    public Task<ChatResponse> GetResponseAsync(
        IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default) =>
        throw new NotSupportedException("This client exists for the streaming path only.");

    public async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        await Task.Yield();
        await cancellation.CancelAsync();
        cancellationToken.ThrowIfCancellationRequested();
        yield break;
    }

    public object? GetService(Type serviceType, object? serviceKey = null) => null;

    public void Dispose()
    {
    }
}
