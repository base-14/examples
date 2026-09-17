using System.Diagnostics.Metrics;
using AgentRebooking.Llm;
using AgentRebooking.Tests.Support;
using Microsoft.Extensions.AI;

namespace AgentRebooking.Tests;

/// <summary>
/// Retry, fallback and cost behaviour of <see cref="GatewayChatClient"/>, exercised
/// against a scripted <see cref="ScriptedChatClient"/> with no remote LLM call. The
/// delay function is injected so these tests run in milliseconds without ever calling
/// the real <see cref="Task.Delay(TimeSpan)"/>; tests that care about the backoff value
/// use <see cref="RecordingDelay"/> to capture what the gateway would have waited.
/// </summary>
public sealed class GatewayChatClientTests
{
    private static readonly Pricing EmptyPricing = Pricing.LoadFromFile("/nonexistent/pricing.json");
    private static readonly GatewayProvider Anthropic = new("anthropic", "claude-sonnet-5");
    private static readonly GatewayProvider OpenAi = new("openai", "gpt-4.1-mini");
    private static readonly GatewayProvider Ollama = new("ollama", "qwen3.5:9b");

    private static string PricingAssetPath =>
        Path.Combine(AppContext.BaseDirectory, "pricing.json");

    private static (Meter Meter, MetricCapture Capture) NewMeter() =>
        BuildMeter($"gateway-test-{Guid.NewGuid()}");

    private static (Meter Meter, MetricCapture Capture) BuildMeter(string name)
    {
        var meter = new Meter(name);
        return (meter, new MetricCapture(meter));
    }

    /// <summary>
    /// A delay function that records every <see cref="TimeSpan"/> the gateway hands it
    /// instead of sleeping, so a test can assert on the real backoff policy's output
    /// rather than trusting that some delay, of some length, happened.
    /// </summary>
    private static (Func<TimeSpan, CancellationToken, Task> Delay, List<TimeSpan> Recorded) RecordingDelay()
    {
        var recorded = new List<TimeSpan>();
        Task Delay(TimeSpan wait, CancellationToken _)
        {
            recorded.Add(wait);
            return Task.CompletedTask;
        }

        return (Delay, recorded);
    }

    [Fact]
    public async Task FailsTwiceThenSucceeds_RecordsTwoRetriesAndNoFallbackOrError()
    {
        var (meter, capture) = NewMeter();
        using (meter)
        using (capture)
        {
            var primary = new ScriptedChatClient(
            [
                ScriptedChatClient.Fails(new InvalidOperationException("transient 1")),
                ScriptedChatClient.Fails(new InvalidOperationException("transient 2")),
                ScriptedChatClient.Succeeds("Hi there!", Anthropic.Model, "msg_1", inputTokens: 12, outputTokens: 5),
            ]);
            var (delay, recordedDelays) = RecordingDelay();

            var client = new GatewayChatClient(
                primary, Anthropic, fallback: null, fallbackInfo: null, EmptyPricing, meter,
                delay: delay);

            var response = await client.GetResponseAsync([new ChatMessage(ChatRole.User, "hello")]);

            Assert.Equal("Hi there!", response.Text);
            Assert.Equal(3, primary.CallCount);

            // Proves the real ExponentialBackoff policy drove the wait, not just that
            // some delay function was called: a broken policy (e.g. always TimeSpan.Zero)
            // would fail this assertion even though the delay itself never sleeps.
            Assert.Equal([TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(2)], recordedDelays);

            Assert.Equal(2, capture.CountOf("base14.gen_ai.retry.count"));
            Assert.Equal(0, capture.CountOf("base14.gen_ai.fallback.count"));
            Assert.Equal(0, capture.CountOf("base14.gen_ai.error.count"));

            var retries = capture.For("base14.gen_ai.retry.count");
            Assert.Equal([1, 2], retries.Select(r => (int)r.Tags["base14.retry.attempt"]!).OrderBy(a => a));
            Assert.All(retries, r =>
            {
                Assert.Equal("anthropic", r.Tags["gen_ai.provider.name"]);
                Assert.Equal("claude-sonnet-5", r.Tags["gen_ai.request.model"]);
                Assert.Equal("InvalidOperationException", r.Tags["error.type"]);
            });
        }
    }

    [Fact]
    public async Task PrimaryAlwaysFails_WithFallbackSet_RecordsFallbackAndReturnsFallbackReply()
    {
        var (meter, capture) = NewMeter();
        using (meter)
        using (capture)
        {
            var primary = new ScriptedChatClient(
            [
                ScriptedChatClient.Fails(new InvalidOperationException("down 1")),
                ScriptedChatClient.Fails(new InvalidOperationException("down 2")),
                ScriptedChatClient.Fails(new InvalidOperationException("down 3")),
            ]);
            var fallback = new ScriptedChatClient(
            [
                ScriptedChatClient.Succeeds("Fallback response", OpenAi.Model, "chatcmpl_1", inputTokens: 10, outputTokens: 4),
            ]);
            var (delay, recordedDelays) = RecordingDelay();

            var client = new GatewayChatClient(
                primary, Anthropic, fallback, OpenAi, EmptyPricing, meter,
                delay: delay);

            var response = await client.GetResponseAsync([new ChatMessage(ChatRole.User, "hello")]);

            Assert.Equal("Fallback response", response.Text);
            Assert.Equal(3, primary.CallCount);
            Assert.Equal(1, fallback.CallCount);
            Assert.Equal([TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(2)], recordedDelays);

            Assert.Equal(2, capture.CountOf("base14.gen_ai.retry.count"));
            Assert.Equal(1, capture.CountOf("base14.gen_ai.fallback.count"));
            Assert.Equal(1, capture.CountOf("base14.gen_ai.error.count"));

            var fallbackMetric = Assert.Single(capture.For("base14.gen_ai.fallback.count"));
            Assert.Equal("anthropic", fallbackMetric.Tags["gen_ai.provider.name"]);
            Assert.Equal("claude-sonnet-5", fallbackMetric.Tags["gen_ai.request.model"]);
            Assert.Equal("openai", fallbackMetric.Tags["base14.gen_ai.fallback.provider"]);

            var errorMetric = Assert.Single(capture.For("base14.gen_ai.error.count"));
            Assert.Equal("anthropic", errorMetric.Tags["gen_ai.provider.name"]);
            Assert.Equal("InvalidOperationException", errorMetric.Tags["error.type"]);

            // Cost is recorded once, for the fallback response only.
            var costMetric = Assert.Single(capture.For("base14.gen_ai.cost"));
            Assert.Equal("openai", costMetric.Tags["gen_ai.provider.name"]);
            Assert.Equal("gpt-4.1-mini", costMetric.Tags["gen_ai.request.model"]);
        }
    }

    [Fact]
    public async Task NoFallbackConfigured_ExhaustsRetriesAndThrows()
    {
        var (meter, capture) = NewMeter();
        using (meter)
        using (capture)
        {
            var primary = new ScriptedChatClient(
            [
                ScriptedChatClient.Fails(new InvalidOperationException("down 1")),
                ScriptedChatClient.Fails(new InvalidOperationException("down 2")),
                ScriptedChatClient.Fails(new InvalidOperationException("down 3")),
            ]);
            var (delay, recordedDelays) = RecordingDelay();

            var client = new GatewayChatClient(
                primary, Anthropic, fallback: null, fallbackInfo: null, EmptyPricing, meter,
                delay: delay);

            await Assert.ThrowsAsync<InvalidOperationException>(
                () => client.GetResponseAsync([new ChatMessage(ChatRole.User, "hello")]));

            Assert.Equal(3, primary.CallCount);
            Assert.Equal([TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(2)], recordedDelays);
            Assert.Equal(2, capture.CountOf("base14.gen_ai.retry.count"));
            Assert.Equal(1, capture.CountOf("base14.gen_ai.error.count"));
            Assert.Equal(0, capture.CountOf("base14.gen_ai.fallback.count"));
        }
    }

    [Fact]
    public async Task CallerCancels_SurfacesCancellationImmediately_WithNoRetryErrorOrFallbackMetrics()
    {
        var (meter, capture) = NewMeter();
        using (meter)
        using (capture)
        {
            var primary = new ScriptedChatClient(
            [
                ScriptedChatClient.Fails(new OperationCanceledException("primary call cancelled")),
            ]);
            var fallback = new ScriptedChatClient(
            [
                ScriptedChatClient.Succeeds("should never run", OpenAi.Model, "chatcmpl_x", inputTokens: 1, outputTokens: 1),
            ]);

            var client = new GatewayChatClient(
                primary, Anthropic, fallback, OpenAi, EmptyPricing, meter,
                backoffPolicy: _ => TimeSpan.Zero,
                delay: (_, _) => Task.CompletedTask);

            using var cts = new CancellationTokenSource();
            cts.Cancel();

            await Assert.ThrowsAsync<OperationCanceledException>(
                () => client.GetResponseAsync(
                    [new ChatMessage(ChatRole.User, "hello")], cancellationToken: cts.Token));

            Assert.Equal(1, primary.CallCount);
            Assert.Equal(0, fallback.CallCount);
            Assert.Equal(0, capture.CountOf("base14.gen_ai.retry.count"));
            Assert.Equal(0, capture.CountOf("base14.gen_ai.error.count"));
            Assert.Equal(0, capture.CountOf("base14.gen_ai.fallback.count"));
        }
    }

    [Fact]
    public async Task InnerClientOwnTimeout_WithoutCallerCancellation_StaysRetryable()
    {
        var (meter, capture) = NewMeter();
        using (meter)
        using (capture)
        {
            // No caller cancellation here, so cancellationToken.IsCancellationRequested is
            // false: this OperationCanceledException reads as an inner client's own
            // timeout, not the caller giving up, and is retried like any other failure.
            var primary = new ScriptedChatClient(
            [
                ScriptedChatClient.Fails(new OperationCanceledException("inner request timed out")),
                ScriptedChatClient.Succeeds("Hi there!", Anthropic.Model, "msg_1", inputTokens: 12, outputTokens: 5),
            ]);

            var client = new GatewayChatClient(
                primary, Anthropic, fallback: null, fallbackInfo: null, EmptyPricing, meter,
                backoffPolicy: _ => TimeSpan.Zero,
                delay: (_, _) => Task.CompletedTask);

            var response = await client.GetResponseAsync([new ChatMessage(ChatRole.User, "hello")]);

            Assert.Equal("Hi there!", response.Text);
            Assert.Equal(2, primary.CallCount);
            Assert.Equal(1, capture.CountOf("base14.gen_ai.retry.count"));
        }
    }

    [Fact]
    public async Task FallbackAlsoFails_RecordsFallbackErrorAndThrowsAggregateWithBothExceptions()
    {
        var (meter, capture) = NewMeter();
        using (meter)
        using (capture)
        {
            var primaryLastException = new InvalidOperationException("primary down 3");
            var fallbackException = new InvalidOperationException("fallback down too");

            var primary = new ScriptedChatClient(
            [
                ScriptedChatClient.Fails(new InvalidOperationException("primary down 1")),
                ScriptedChatClient.Fails(new InvalidOperationException("primary down 2")),
                ScriptedChatClient.Fails(primaryLastException),
            ]);
            var fallback = new ScriptedChatClient(
            [
                ScriptedChatClient.Fails(fallbackException),
            ]);

            var client = new GatewayChatClient(
                primary, Anthropic, fallback, OpenAi, EmptyPricing, meter,
                backoffPolicy: _ => TimeSpan.Zero,
                delay: (_, _) => Task.CompletedTask);

            var thrown = await Assert.ThrowsAsync<AggregateException>(
                () => client.GetResponseAsync([new ChatMessage(ChatRole.User, "hello")]));

            Assert.Equal(2, thrown.InnerExceptions.Count);
            Assert.Contains(primaryLastException, thrown.InnerExceptions);
            Assert.Contains(fallbackException, thrown.InnerExceptions);

            Assert.Equal(1, fallback.CallCount);

            // The primary's exhausted-retry error and the fallback's own error are both
            // recorded; neither exception is silently dropped.
            Assert.Equal(2, capture.CountOf("base14.gen_ai.error.count"));
            var fallbackError = Assert.Single(
                capture.For("base14.gen_ai.error.count"), m => Equals(m.Tags["gen_ai.provider.name"], "openai"));
            Assert.Equal("gpt-4.1-mini", fallbackError.Tags["gen_ai.request.model"]);
            Assert.Equal("InvalidOperationException", fallbackError.Tags["error.type"]);
        }
    }

    [Fact]
    public async Task KnownOpenAiModel_RecordsCostFromPricingJson()
    {
        var (meter, capture) = NewMeter();
        using (meter)
        using (capture)
        {
            var pricing = Pricing.LoadFromFile(PricingAssetPath);
            var primary = new ScriptedChatClient(
            [
                ScriptedChatClient.Succeeds(
                    "hello", OpenAi.Model, "chatcmpl_1", inputTokens: 1_000_000, outputTokens: 1_000_000),
            ]);

            var client = new GatewayChatClient(primary, OpenAi, fallback: null, fallbackInfo: null, pricing, meter);

            await client.GetResponseAsync([new ChatMessage(ChatRole.User, "hello")]);

            // gpt-4.1-mini in _shared/pricing.json: input 0.4/M, output 1.6/M.
            var expected = pricing.CostFor(OpenAi.Name, OpenAi.Model,
                new UsageDetails { InputTokenCount = 1_000_000, OutputTokenCount = 1_000_000 });
            Assert.Equal(2.0, expected, precision: 6);

            var costMetric = Assert.Single(capture.For("base14.gen_ai.cost"));
            Assert.Equal(expected, costMetric.Value, precision: 6);
            Assert.Equal("openai", costMetric.Tags["gen_ai.provider.name"]);
            Assert.Equal("gpt-4.1-mini", costMetric.Tags["gen_ai.request.model"]);
        }
    }

    [Fact]
    public async Task OllamaModel_NotInPricingTable_YieldsZeroCost()
    {
        var (meter, capture) = NewMeter();
        using (meter)
        using (capture)
        {
            var pricing = Pricing.LoadFromFile(PricingAssetPath);
            var primary = new ScriptedChatClient(
            [
                ScriptedChatClient.Succeeds("hi", Ollama.Model, "resp_1", inputTokens: 1000, outputTokens: 500),
            ]);

            var client = new GatewayChatClient(primary, Ollama, fallback: null, fallbackInfo: null, pricing, meter);

            await client.GetResponseAsync([new ChatMessage(ChatRole.User, "hello")]);

            var costMetric = Assert.Single(capture.For("base14.gen_ai.cost"));
            Assert.Equal(0d, costMetric.Value);
            Assert.Equal("ollama", costMetric.Tags["gen_ai.provider.name"]);
            Assert.Equal("qwen3.5:9b", costMetric.Tags["gen_ai.request.model"]);
        }
    }

    [Fact]
    public async Task CallerCancelsDuringLastAttempt_DoesNotReachFallback()
    {
        var (meter, capture) = NewMeter();
        using (meter)
        using (capture)
        {
            using var cts = new CancellationTokenSource();

            // The third failure is not a cancellation, but the caller's token cancels
            // alongside it. The gateway must not hand that dead token to the fallback.
            var primary = new ScriptedChatClient(
            [
                ScriptedChatClient.Fails(new InvalidOperationException("transient 1")),
                ScriptedChatClient.Fails(new InvalidOperationException("transient 2")),
                () =>
                {
                    cts.Cancel();
                    throw new InvalidOperationException("transient 3");
                },
            ]);
            var fallback = new ScriptedChatClient(
            [
                ScriptedChatClient.Succeeds("should never run", OpenAi.Model, "chatcmpl_x", inputTokens: 1, outputTokens: 1),
            ]);

            var client = new GatewayChatClient(
                primary, Anthropic, fallback, OpenAi, EmptyPricing, meter,
                backoffPolicy: _ => TimeSpan.Zero,
                delay: (_, _) => Task.CompletedTask);

            await Assert.ThrowsAsync<OperationCanceledException>(
                () => client.GetResponseAsync(
                    [new ChatMessage(ChatRole.User, "hello")], cancellationToken: cts.Token));

            Assert.Equal(3, primary.CallCount);
            Assert.Equal(0, fallback.CallCount);
            Assert.Equal(0, capture.CountOf("base14.gen_ai.fallback.count"));
            Assert.Equal(1, capture.CountOf("base14.gen_ai.error.count"));
        }
    }

    /// <summary>
    /// The streaming path is the one a live run takes, so an outage has to be counted there
    /// or base14.gen_ai.error.count reads as a healthy zero while every run is failing. One
    /// attempt, one error, no retry and no fallback: the reasoning is on the override.
    /// </summary>
    [Fact]
    public async Task AFailedStreamingCall_CountsOneErrorAndDoesNotRetryOrFallBack()
    {
        var (meter, capture) = NewMeter();
        using (meter)
        using (capture)
        {
            var primary = new ScriptedChatClient([ScriptedChatClient.Fails(new HttpRequestException("no route"))]);
            var fallback = new ScriptedChatClient(
            [
                ScriptedChatClient.Succeeds("never reached", OpenAi.Model, "chatcmpl_1", inputTokens: 1, outputTokens: 1),
            ]);
            var (delay, recordedDelays) = RecordingDelay();

            var client = new GatewayChatClient(
                primary, Ollama, fallback, OpenAi, EmptyPricing, meter, delay: delay);

            await Assert.ThrowsAsync<HttpRequestException>(async () =>
            {
                await foreach (var _ in client.GetStreamingResponseAsync([new ChatMessage(ChatRole.User, "hello")]))
                {
                }
            });

            Assert.Equal(1, primary.CallCount);
            Assert.Equal(0, fallback.CallCount);
            Assert.Empty(recordedDelays);

            Assert.Equal(0, capture.CountOf("base14.gen_ai.retry.count"));
            Assert.Equal(0, capture.CountOf("base14.gen_ai.fallback.count"));
            Assert.Equal(1, capture.CountOf("base14.gen_ai.error.count"));

            var errorMetric = Assert.Single(capture.For("base14.gen_ai.error.count"));
            Assert.Equal("ollama", errorMetric.Tags["gen_ai.provider.name"]);
            Assert.Equal("qwen3.5:9b", errorMetric.Tags["gen_ai.request.model"]);
            Assert.Equal("HttpRequestException", errorMetric.Tags["error.type"]);
        }
    }

    /// <summary>
    /// A cancelled run is not a provider failure, on the streaming path for the same reason
    /// it is not on the other one. Without the exclusion every timed-out run would inflate
    /// the error counter and point a reader at the model.
    /// </summary>
    [Fact]
    public async Task ACancelledStreamingCall_CountsNoError()
    {
        var (meter, capture) = NewMeter();
        using (meter)
        using (capture)
        {
            using var cancellation = new CancellationTokenSource();
            var primary = new CancellingChatClient(cancellation);

            var client = new GatewayChatClient(
                primary, Ollama, fallback: null, fallbackInfo: null, EmptyPricing, meter);

            await Assert.ThrowsAnyAsync<OperationCanceledException>(async () =>
            {
                await foreach (var _ in client.GetStreamingResponseAsync(
                    [new ChatMessage(ChatRole.User, "hello")], cancellationToken: cancellation.Token))
                {
                }
            });

            Assert.Equal(0, capture.CountOf("base14.gen_ai.error.count"));
        }
    }

    /// <summary>
    /// A stream that fails before it opens is counted once, on the same counter and with the
    /// same tags as one that fails partway through. Without the acquisition inside the try
    /// this error would leave no measurement at all, which is the shape of defect that made
    /// this override necessary in the first place.
    /// </summary>
    [Fact]
    public async Task AStreamThatFailsBeforeItOpens_IsStillCountedOnce()
    {
        var (meter, capture) = NewMeter();
        using (meter)
        using (capture)
        {
            var primary = new FailingToOpenChatClient(new HttpRequestException("no route"));

            var client = new GatewayChatClient(
                primary, Ollama, fallback: null, fallbackInfo: null, EmptyPricing, meter);

            await Assert.ThrowsAsync<HttpRequestException>(async () =>
            {
                await foreach (var _ in client.GetStreamingResponseAsync([new ChatMessage(ChatRole.User, "hello")]))
                {
                }
            });

            Assert.Equal(1, capture.CountOf("base14.gen_ai.error.count"));

            var errorMetric = Assert.Single(capture.For("base14.gen_ai.error.count"));
            Assert.Equal("ollama", errorMetric.Tags["gen_ai.provider.name"]);
            Assert.Equal("HttpRequestException", errorMetric.Tags["error.type"]);
        }
    }

    /// <summary>
    /// The cancellation exclusion covers the opening call as well, not only the updates.
    /// </summary>
    [Fact]
    public async Task AStreamCancelledBeforeItOpens_CountsNoError()
    {
        var (meter, capture) = NewMeter();
        using (meter)
        using (capture)
        {
            using var cancellation = new CancellationTokenSource();
            await cancellation.CancelAsync();

            var primary = new FailingToOpenChatClient(new OperationCanceledException(cancellation.Token));

            var client = new GatewayChatClient(
                primary, Ollama, fallback: null, fallbackInfo: null, EmptyPricing, meter);

            await Assert.ThrowsAnyAsync<OperationCanceledException>(async () =>
            {
                await foreach (var _ in client.GetStreamingResponseAsync(
                    [new ChatMessage(ChatRole.User, "hello")], cancellationToken: cancellation.Token))
                {
                }
            });

            Assert.Equal(0, capture.CountOf("base14.gen_ai.error.count"));
        }
    }

    [Theory]
    [InlineData(1, 1)]
    [InlineData(2, 2)]
    [InlineData(4, 3)]
    [InlineData(8, 4)]
    [InlineData(10, 5)]
    [InlineData(10, 6)]
    public void ExponentialBackoff_IsClampedBetweenOneAndTenSeconds(double expectedSeconds, int attempt)
    {
        Assert.Equal(TimeSpan.FromSeconds(expectedSeconds), GatewayChatClient.ExponentialBackoff(attempt));
    }
}
