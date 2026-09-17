using System.Runtime.CompilerServices;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;

namespace AgentRebooking.Tests.Support;

/// <summary>
/// Plays a fixed sequence of assistant turns back to the agents so the whole handoff
/// workflow runs in process with no model behind it. One instance serves both agents: the
/// turns are consumed in the order the workflow takes them, triage first.
/// </summary>
internal sealed class ScriptedAgentChatClient(IEnumerable<ChatMessage> turns) : IChatClient
{
    private readonly Queue<ChatMessage> _turns = new(turns);
    private readonly Lock _sync = new();

    public int CallCount { get; private set; }

    public static ChatMessage ToolCall(string toolName, params (string Key, object? Value)[] arguments) =>
        new(ChatRole.Assistant,
        [
            new FunctionCallContent(
                Guid.NewGuid().ToString("N")[..8],
                toolName,
                arguments.ToDictionary(argument => argument.Key, argument => argument.Value)),
        ]);

    /// <summary>One assistant turn that calls several tools at once.</summary>
    public static ChatMessage ToolCalls(params ChatMessage[] calls) =>
        new(ChatRole.Assistant, [.. calls.SelectMany(call => call.Contents)]);

    public static ChatMessage Reply(string text) => new(ChatRole.Assistant, text);

    public Task<ChatResponse> GetResponseAsync(
        IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default) =>
        Task.FromResult(new ChatResponse(Next())
        {
            ModelId = "scripted",
            ResponseId = Guid.NewGuid().ToString("N"),
            FinishReason = ChatFinishReason.Stop,
        });

    public async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var responseId = Guid.NewGuid().ToString("N");
        var message = Next();

        yield return new ChatResponseUpdate(ChatRole.Assistant, message.Contents)
        {
            ModelId = "scripted",
            ResponseId = responseId,
            MessageId = responseId,
            FinishReason = ChatFinishReason.Stop,
        };

        await Task.CompletedTask;
    }

    public object? GetService(Type serviceType, object? serviceKey = null) => null;

    public void Dispose()
    {
    }

    private ChatMessage Next()
    {
        lock (_sync)
        {
            CallCount++;

            return _turns.Count > 0
                ? _turns.Dequeue()
                : throw new InvalidOperationException(
                    $"The scripted chat client ran out of turns on call {CallCount}.");
        }
    }
}

/// <summary>
/// Holds its first turn open until released or cancelled, so a run stays in
/// <c>running</c> long enough for the run timeout to be exercised.
/// </summary>
internal sealed class BlockingChatClient : IChatClient
{
    private readonly TaskCompletionSource _release = new(TaskCreationOptions.RunContinuationsAsynchronously);

    public void Release() => _release.TrySetResult();

    public async Task<ChatResponse> GetResponseAsync(
        IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
    {
        await _release.Task.WaitAsync(cancellationToken);
        return new ChatResponse(new ChatMessage(ChatRole.Assistant, "released"));
    }

    public async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        await _release.Task.WaitAsync(cancellationToken);
        yield return new ChatResponseUpdate(ChatRole.Assistant, "released");
    }

    public object? GetService(Type serviceType, object? serviceKey = null) => null;

    public void Dispose() => Release();
}

/// <summary>
/// Delegates to an inner client but holds one nominated turn open until released, so a test
/// can act while a run is genuinely still running instead of racing it to the finish.
/// </summary>
internal sealed class PausingChatClient(IChatClient inner, int pauseOnTurn) : IChatClient
{
    private readonly TaskCompletionSource _reached = new(TaskCreationOptions.RunContinuationsAsynchronously);
    private readonly TaskCompletionSource _release = new(TaskCreationOptions.RunContinuationsAsynchronously);
    private int _turns;

    /// <summary>Completes once the run has reached the nominated turn and is being held there.</summary>
    public Task Reached => _reached.Task;

    public void Release() => _release.TrySetResult();

    public async Task<ChatResponse> GetResponseAsync(
        IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
    {
        await PauseIfNominatedAsync(cancellationToken);
        return await inner.GetResponseAsync(messages, options, cancellationToken);
    }

    public async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        await PauseIfNominatedAsync(cancellationToken);

        await foreach (var update in inner.GetStreamingResponseAsync(messages, options, cancellationToken))
        {
            yield return update;
        }
    }

    public object? GetService(Type serviceType, object? serviceKey = null) =>
        inner.GetService(serviceType, serviceKey);

    public void Dispose()
    {
        Release();
        inner.Dispose();
    }

    private async Task PauseIfNominatedAsync(CancellationToken cancellationToken)
    {
        if (Interlocked.Increment(ref _turns) != pauseOnTurn)
        {
            return;
        }

        _reached.TrySetResult();
        await _release.Task.WaitAsync(cancellationToken);
    }
}

/// <summary>
/// Holds its caller at the first log call whose message template is exactly
/// <paramref name="template"/>, until released.
/// </summary>
/// <remarks>
/// The run store logs the pending approval from inside its own pass over the stream, and
/// that log call is the last thing the pass does before leaving it. Pausing there is the
/// only way in from outside to hold a pass open on a run that has a pending request to
/// answer, which is the state every handover race needs. The gate, and so the price lookup,
/// runs before the request is published, and any request the pass raises afterwards is
/// refused before the gate is reached.
/// <para>
/// Matched against the template, not the formatted text: structured logging keeps the
/// original format string on the state under the "{OriginalFormat}" key, so this holds on
/// the exact call site rather than on words that happen to appear in the rendered message.
/// </para>
/// </remarks>
internal sealed class PausingLogger<T>(string template) : ILogger<T>
{
    private static readonly TimeSpan Backstop = TimeSpan.FromSeconds(30);

    private readonly TaskCompletionSource _reached = new(TaskCreationOptions.RunContinuationsAsynchronously);
    private readonly TaskCompletionSource _release = new(TaskCreationOptions.RunContinuationsAsynchronously);

    /// <summary>Completes once the caller has reached the message and is being held there.</summary>
    public Task Reached => _reached.Task;

    public void Release() => _release.TrySetResult();

    public IDisposable? BeginScope<TState>(TState state)
        where TState : notnull => null;

    public bool IsEnabled(LogLevel logLevel) => true;

    public void Log<TState>(
        LogLevel logLevel,
        EventId eventId,
        TState state,
        Exception? exception,
        Func<TState, Exception?, string> formatter)
    {
        if (state is not IReadOnlyList<KeyValuePair<string, object>> fields
            || fields.FirstOrDefault(field => field.Key == "{OriginalFormat}").Value as string != template)
        {
            return;
        }

        _reached.TrySetResult();

        // ILogger.Log is synchronous, so this blocks the pass's thread, which is the point.
        // The backstop means a test that never releases fails rather than hangs the run.
        _release.Task.Wait(Backstop);
    }
}

/// <summary>
/// A clock the tests move by hand, so approval expiry, the run timeout and TTL eviction are
/// asserted without waiting on a real one.
/// </summary>
internal sealed class TestTimeProvider(DateTimeOffset start) : TimeProvider
{
    private readonly Lock _sync = new();
    private DateTimeOffset _now = start;

    public TestTimeProvider()
        : this(new DateTimeOffset(2026, 9, 15, 12, 0, 0, TimeSpan.Zero))
    {
    }

    public override DateTimeOffset GetUtcNow()
    {
        lock (_sync)
        {
            return _now;
        }
    }

    public void Advance(TimeSpan amount)
    {
        lock (_sync)
        {
            _now = _now.Add(amount);
        }
    }
}
