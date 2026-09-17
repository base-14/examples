using System.Diagnostics.Metrics;
using System.Runtime.CompilerServices;
using System.Runtime.ExceptionServices;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace AgentRebooking.Llm;

/// <summary>
/// The provider and model a <see cref="GatewayChatClient"/> is calling, used to label
/// the four gateway metrics.
/// </summary>
public sealed record GatewayProvider(string Name, string Model);

/// <summary>
/// A <see cref="DelegatingChatClient"/> that wraps a primary provider client with retry,
/// fallback and cost tracking the framework does not provide on its own. Three attempts
/// with exponential backoff on any exception; when every attempt on the primary fails and
/// a fallback client is configured, the call is retried once against the fallback. Emits
/// base14.gen_ai.cost, base14.gen_ai.retry.count, base14.gen_ai.fallback.count and
/// base14.gen_ai.error.count on the meter it is given, each carrying gen_ai.provider.name
/// and gen_ai.request.model.
/// </summary>
/// <remarks>
/// Retry, fallback and cost are on <see cref="GetResponseAsync"/> only. The agent framework
/// streams, so a live run takes <see cref="GetStreamingResponseAsync"/> and those three stay at
/// zero here; only the tests exercise them.
/// </remarks>
public sealed class GatewayChatClient : DelegatingChatClient
{
    private const int MaxAttempts = 3;

    private readonly IChatClient _primary;
    private readonly GatewayProvider _primaryInfo;
    private readonly IChatClient? _fallback;
    private readonly GatewayProvider? _fallbackInfo;
    private readonly Pricing _pricing;
    private readonly ILogger<GatewayChatClient> _logger;
    private readonly Func<int, TimeSpan> _backoffPolicy;
    private readonly Func<TimeSpan, CancellationToken, Task> _delay;

    private readonly Counter<double> _costCounter;
    private readonly Counter<long> _retryCounter;
    private readonly Counter<long> _fallbackCounter;
    private readonly Counter<long> _errorCounter;

    private bool _disposed;

    public GatewayChatClient(
        IChatClient primary,
        GatewayProvider primaryInfo,
        IChatClient? fallback,
        GatewayProvider? fallbackInfo,
        Pricing pricing,
        Meter meter,
        ILogger<GatewayChatClient>? logger = null,
        Func<int, TimeSpan>? backoffPolicy = null,
        Func<TimeSpan, CancellationToken, Task>? delay = null)
        : base(primary)
    {
        if (fallback is not null && fallbackInfo is null)
        {
            throw new ArgumentException(
                "fallbackInfo is required when a fallback client is set.", nameof(fallbackInfo));
        }

        _primary = primary;
        _primaryInfo = primaryInfo;
        _fallback = fallback;
        _fallbackInfo = fallbackInfo;
        _pricing = pricing;
        _logger = logger ?? NullLogger<GatewayChatClient>.Instance;
        _backoffPolicy = backoffPolicy ?? ExponentialBackoff;
        _delay = delay ?? ((wait, cancellationToken) => Task.Delay(wait, cancellationToken));

        _costCounter = meter.CreateCounter<double>("base14.gen_ai.cost", unit: "usd");
        _retryCounter = meter.CreateCounter<long>("base14.gen_ai.retry.count", unit: "{retry}");
        _fallbackCounter = meter.CreateCounter<long>("base14.gen_ai.fallback.count", unit: "{fallback}");
        _errorCounter = meter.CreateCounter<long>("base14.gen_ai.error.count", unit: "{error}");
    }

    /// <summary>Exponential backoff, 2^(attempt-1) seconds clamped to ten.</summary>
    public static TimeSpan ExponentialBackoff(int retryAttempt) =>
        TimeSpan.FromSeconds(Math.Min(10, Math.Pow(2, Math.Max(0, retryAttempt - 1))));

    public override async Task<ChatResponse> GetResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        Exception? lastException = null;

        for (var attempt = 1; attempt <= MaxAttempts; attempt++)
        {
            try
            {
                var response = await _primary.GetResponseAsync(messages, options, cancellationToken)
                    .ConfigureAwait(false);
                RecordCost(_primaryInfo, response);
                return response;
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                // The caller cancelled: not a provider failure, and the cancelled token must
                // not reach another client. An inner client's own timeout falls through below.
                throw;
            }
            catch (Exception ex)
            {
                lastException = ex;
                _logger.LogWarning(
                    ex, "GatewayChatClient attempt {Attempt} against {Provider} failed with {ExceptionType}",
                    attempt, _primaryInfo.Name, ex.GetType().Name);

                if (attempt < MaxAttempts)
                {
                    RecordRetry(_primaryInfo, ex, attempt);
                    await _delay(_backoffPolicy(attempt), cancellationToken).ConfigureAwait(false);
                }
            }
        }

        RecordError(_primaryInfo, lastException!);

        if (_fallback is null)
        {
            ExceptionDispatchInfo.Capture(lastException!).Throw();
            throw lastException!; // unreachable; Throw() above always throws
        }

        // A primary failure can still race with the caller cancelling, and the fallback is the
        // hosted provider in a deployed configuration.
        cancellationToken.ThrowIfCancellationRequested();

        RecordFallback(_primaryInfo, _fallbackInfo!);

        try
        {
            var fallbackResponse = await _fallback.GetResponseAsync(messages, options, cancellationToken)
                .ConfigureAwait(false);
            RecordCost(_fallbackInfo!, fallbackResponse);
            return fallbackResponse;
        }
        catch (Exception fallbackException)
        {
            RecordError(_fallbackInfo!, fallbackException);
            throw new AggregateException(
                $"Primary provider '{_primaryInfo.Name}' and fallback provider '{_fallbackInfo!.Name}' both failed.",
                lastException!,
                fallbackException);
        }
    }

    /// <summary>
    /// Counts a failed streaming call on <c>base14.gen_ai.error.count</c> and lets it through.
    /// </summary>
    /// <remarks>
    /// This is the path a live run takes, so without the override a provider outage left the
    /// error counter at a healthy-looking zero. Counted, not retried: a faulted stream may
    /// already have yielded updates that became a tool call, so replaying it would repeat work.
    /// </remarks>
    public override async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        // Never fires on a compiler-generated iterator, which does nothing until the first
        // MoveNextAsync. An inner client that validated arguments up front would throw here.
        IAsyncEnumerator<ChatResponseUpdate> updates;

        try
        {
            updates = _primary
                .GetStreamingResponseAsync(messages, options, cancellationToken)
                .GetAsyncEnumerator(cancellationToken);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception ex)
        {
            _logger.LogWarning(
                ex, "GatewayChatClient could not open a stream against {Provider}: {ExceptionType}",
                _primaryInfo.Name, ex.GetType().Name);
            RecordError(_primaryInfo, ex);
            throw;
        }

        // DisposeAsync is not counted: closing a stream that delivered its updates is not a
        // failed provider call.
        await using var owned = updates.ConfigureAwait(false);

        while (true)
        {
            ChatResponseUpdate update;

            try
            {
                if (!await updates.MoveNextAsync().ConfigureAwait(false))
                {
                    yield break;
                }

                update = updates.Current;
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                // Same exclusion GetResponseAsync makes: a timed-out run is not a provider error.
                throw;
            }
            catch (Exception ex)
            {
                _logger.LogWarning(
                    ex, "GatewayChatClient streaming call against {Provider} failed with {ExceptionType}",
                    _primaryInfo.Name, ex.GetType().Name);
                RecordError(_primaryInfo, ex);
                throw;
            }

            yield return update;
        }
    }

    private void RecordCost(GatewayProvider provider, ChatResponse response)
    {
        var cost = _pricing.CostFor(provider.Name, provider.Model, response.Usage);
        _costCounter.Add(
            cost,
            new KeyValuePair<string, object?>("gen_ai.provider.name", provider.Name),
            new KeyValuePair<string, object?>("gen_ai.request.model", provider.Model));
    }

    private void RecordRetry(GatewayProvider provider, Exception exception, int attempt)
    {
        _retryCounter.Add(
            1,
            new KeyValuePair<string, object?>("gen_ai.provider.name", provider.Name),
            new KeyValuePair<string, object?>("gen_ai.request.model", provider.Model),
            new KeyValuePair<string, object?>("error.type", exception.GetType().Name),
            new KeyValuePair<string, object?>("base14.retry.attempt", attempt));
    }

    private void RecordError(GatewayProvider provider, Exception exception)
    {
        _errorCounter.Add(
            1,
            new KeyValuePair<string, object?>("gen_ai.provider.name", provider.Name),
            new KeyValuePair<string, object?>("gen_ai.request.model", provider.Model),
            new KeyValuePair<string, object?>("error.type", exception.GetType().Name));
    }

    private void RecordFallback(GatewayProvider primary, GatewayProvider fallback)
    {
        _fallbackCounter.Add(
            1,
            new KeyValuePair<string, object?>("gen_ai.provider.name", primary.Name),
            new KeyValuePair<string, object?>("gen_ai.request.model", primary.Model),
            new KeyValuePair<string, object?>("base14.gen_ai.fallback.provider", fallback.Name));
    }

    // base(primary) disposes only the primary client; the fallback is ours to close.
    protected override void Dispose(bool disposing)
    {
        if (_disposed)
        {
            return;
        }

        if (disposing)
        {
            _fallback?.Dispose();
        }

        _disposed = true;
        base.Dispose(disposing);
    }
}
