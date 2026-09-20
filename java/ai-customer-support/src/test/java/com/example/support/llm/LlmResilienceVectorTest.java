package com.example.support.llm;

import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;

import com.fasterxml.jackson.databind.JsonNode;

import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.sdk.metrics.data.LongPointData;
import io.opentelemetry.sdk.metrics.data.MetricData;
import io.opentelemetry.sdk.trace.data.EventData;
import io.opentelemetry.sdk.trace.data.SpanData;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import org.springframework.ai.chat.messages.AssistantMessage;
import org.springframework.ai.chat.messages.UserMessage;
import org.springframework.ai.chat.metadata.ChatGenerationMetadata;
import org.springframework.ai.chat.metadata.ChatResponseMetadata;
import org.springframework.ai.chat.metadata.DefaultUsage;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.ai.chat.model.Generation;
import org.springframework.ai.chat.prompt.Prompt;
import org.springframework.ai.model.tool.ToolCallingManager;
import org.springframework.ai.model.tool.ToolExecutionResult;

import com.example.support.config.AppConfig;
import com.example.support.telemetry.ConversationScope;
import com.example.support.telemetry.GenAi;
import com.example.support.telemetry.TestOtel;
import com.example.support.telemetry.TestVectors;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * Retry and fallback behaviour against {@code _shared/test-vectors/chat-with-retry.json}
 * and {@code chat-with-fallback.json}, asserted on the metrics the SDK exports.
 */
class LlmResilienceVectorTest {

    private static final String CONVERSATION_ID = "conv-1";
    private static final int MAX_TOOL_ROUNDS = 8;

    private final TestOtel otel = new TestOtel();
    private final ConversationScope conversations = new ConversationScope();

    @AfterEach
    void tearDown() {
        conversations.end();
        otel.close();
    }

    /** Events only land when a conversation is open, so every case opens one. */
    private Span beginConversation() {
        Span span = otel.sdk().getTracer("test").spanBuilder("support_conversation").startSpan();
        conversations.begin(CONVERSATION_ID, span);
        return span;
    }

    @Test
    void retrySucceedsWithoutFallback() {
        JsonNode vector = TestVectors.load("chat-with-retry.json");
        JsonNode setup = vector.get("setup");
        JsonNode success = vector.get("mock_behavior").get("attempt_2");

        Span conversation = beginConversation();
        ChatModel primary = mock(ChatModel.class);
        ChatModel fallback = mock(ChatModel.class);
        when(primary.call(any(Prompt.class)))
            .thenThrow(new RuntimeException("Rate limit"))
            .thenReturn(chatResponse(success));

        LlmResponse response = service(setup, primary, fallback)
            .generateCapable("You are helpful.", "Hello");
        conversation.end();

        assertEquals(success.get("content").asText(), response.content());
        assertEquals(success.get("input_tokens").asInt(), response.inputTokens());
        assertEquals(success.get("output_tokens").asInt(), response.outputTokens());
        verify(primary, times(2)).call(any(Prompt.class));
        verify(fallback, times(0)).call(any(Prompt.class));

        LongPointData retry = onlyLongPoint("base14.gen_ai.retry.count");
        assertEquals(expectedMetricValue(vector, "base14.gen_ai.retry.count"), retry.getValue());
        assertEquals(setup.get("provider").asText(),
            retry.getAttributes().get(AttributeKey.stringKey("gen_ai.provider.name")));
        assertEquals("RuntimeException", retry.getAttributes().get(AttributeKey.stringKey("error.type")));
        assertEquals(1L, retry.getAttributes().get(AttributeKey.longKey("base14.retry.attempt")));

        assertTrue(metric("base14.gen_ai.fallback.count").isEmpty(), "retry succeeded, no fallback");
        assertTrue(conversationEvents(GenAi.FALLBACK_EVENT).isEmpty(), "retry succeeded, no fallback event");
        assertTrue(metric("base14.gen_ai.error.count").isEmpty(), "retry succeeded, no error");
        assertTrue(metric("gen_ai.client.operation.duration").isPresent());
    }

    @Test
    void fallbackTakesOverWhenThePrimaryIsExhausted() {
        JsonNode vector = TestVectors.load("chat-with-fallback.json");
        JsonNode setup = vector.get("setup");
        JsonNode success = vector.get("mock_behavior").get("fallback");

        Span conversation = beginConversation();
        ChatModel primary = mock(ChatModel.class);
        ChatModel fallback = mock(ChatModel.class);
        when(primary.call(any(Prompt.class))).thenThrow(new RuntimeException("Service unavailable"));
        when(fallback.call(any(Prompt.class))).thenReturn(chatResponse(success));

        LlmResponse response = service(fallbackSetup(setup), primary, fallback)
            .generateCapable("You are helpful.", "Hello");
        conversation.end();

        assertEquals(success.get("content").asText(), response.content());
        assertEquals(setup.get("fallback_provider").asText(), response.provider());
        verify(primary, times(3)).call(any(Prompt.class));
        verify(fallback, times(1)).call(any(Prompt.class));

        assertEquals(expectedMetricValue(vector, "base14.gen_ai.retry.count"),
            sum("base14.gen_ai.retry.count"));

        LongPointData fallbackPoint = onlyLongPoint("base14.gen_ai.fallback.count");
        assertEquals(expectedMetricValue(vector, "base14.gen_ai.fallback.count"), fallbackPoint.getValue());
        assertEquals(setup.get("primary_provider").asText(),
            fallbackPoint.getAttributes().get(AttributeKey.stringKey("gen_ai.provider.name")));
        assertEquals(setup.get("fallback_provider").asText(),
            fallbackPoint.getAttributes().get(AttributeKey.stringKey("base14.gen_ai.fallback.provider")));

        LongPointData error = onlyLongPoint("base14.gen_ai.error.count");
        assertEquals(expectedMetricValue(vector, "base14.gen_ai.error.count"), error.getValue());
        assertEquals(setup.get("primary_provider").asText(),
            error.getAttributes().get(AttributeKey.stringKey("gen_ai.provider.name")));
        assertEquals("RuntimeException", error.getAttributes().get(AttributeKey.stringKey("error.type")));

        List<EventData> events = conversationEvents(GenAi.FALLBACK_EVENT);
        assertEquals(1, events.size(), "one provider_fallback event on the conversation span");
        var attributes = events.getFirst().getAttributes();
        assertEquals(Boolean.TRUE,
            attributes.get(AttributeKey.booleanKey(GenAi.FALLBACK_TRIGGERED)));
        assertEquals(setup.get("primary_provider").asText(),
            attributes.get(AttributeKey.stringKey("gen_ai.provider.name")));
        assertEquals(setup.get("fallback_provider").asText(),
            attributes.get(AttributeKey.stringKey("base14.gen_ai.fallback.provider")));
    }

    /**
     * The shipped default points LLM_PROVIDER and FALLBACK_PROVIDER at the same Ollama
     * model, where a fallback would only repeat the primary's three attempts.
     */
    @Test
    void aFallbackOntoTheSameProviderAndModelIsSkipped() {
        Span conversation = beginConversation();
        ChatModel ollama = mock(ChatModel.class);
        when(ollama.call(any(Prompt.class))).thenThrow(new RuntimeException("Service unavailable"));

        LlmService service = sameTargetService(ollama);
        RuntimeException failure = assertThrows(RuntimeException.class,
            () -> service.generateCapable("You are helpful.", "Hello"));
        conversation.end();

        assertEquals("Service unavailable", failure.getMessage());
        verify(ollama, times(3)).call(any(Prompt.class));
        assertTrue(metric("base14.gen_ai.fallback.count").isEmpty(), "no fallback onto the same target");
        assertTrue(conversationEvents(GenAi.FALLBACK_EVENT).isEmpty(), "no provider_fallback event");
        assertEquals(1L, sum("base14.gen_ai.error.count"));
    }

    /**
     * The tool loop cap must not hand back a tool-call-only message: callers such as
     * IntentClassifier and the PII filter dereference the content.
     */
    @Test
    void theToolLoopCapStillProducesText() {
        JsonNode setup = TestVectors.load("chat-with-retry.json").get("setup");

        Span conversation = beginConversation();
        ChatModel primary = mock(ChatModel.class);
        when(primary.call(any(Prompt.class))).thenReturn(toolCallResponse());

        LlmResponse response = service(setup, primary, mock(ChatModel.class), loopingToolManager())
            .generateCapable("You are helpful.", "Hello");
        conversation.end();

        assertNotNull(response.content(), "content is never null");
        assertFalse(response.content().isBlank(), "content is never blank");
        // The initial call, eight tool rounds, and the final call with the tools taken away.
        verify(primary, times(MAX_TOOL_ROUNDS + 2)).call(any(Prompt.class));

        List<EventData> events = conversationEvents(GenAi.TOOL_LOOP_LIMIT_EVENT);
        assertEquals(1, events.size(), "one tool_loop_limit_reached event on the conversation span");
        assertEquals((long) MAX_TOOL_ROUNDS,
            events.getFirst().getAttributes().get(AttributeKey.longKey(GenAi.TOOL_LOOP_ROUNDS)));
    }

    @Test
    void theFinalToolFreeAnswerIsUsedWhenTheModelGivesOne() {
        JsonNode setup = TestVectors.load("chat-with-retry.json").get("setup");

        Span conversation = beginConversation();
        AtomicInteger calls = new AtomicInteger();
        ChatModel primary = mock(ChatModel.class);
        // The initial call and the eight tool rounds ask for tools; the last call is the
        // tool-free one the cap makes.
        when(primary.call(any(Prompt.class))).thenAnswer(invocation ->
            calls.incrementAndGet() <= MAX_TOOL_ROUNDS + 1
                ? toolCallResponse()
                : textResponse("Here is what I found so far."));

        LlmResponse response = service(setup, primary, mock(ChatModel.class), loopingToolManager())
            .generateCapable("You are helpful.", "Hello");
        conversation.end();

        assertEquals("Here is what I found so far.", response.content());
        assertEquals(1, conversationEvents(GenAi.TOOL_LOOP_LIMIT_EVENT).size());
    }

    private static ToolCallingManager loopingToolManager() {
        ToolCallingManager manager = mock(ToolCallingManager.class);
        ToolExecutionResult result = mock(ToolExecutionResult.class);
        when(result.returnDirect()).thenReturn(false);
        when(result.conversationHistory()).thenReturn(List.of(new UserMessage("Hello")));
        when(manager.executeToolCalls(any(Prompt.class), any(ChatResponse.class))).thenReturn(result);
        return manager;
    }

    private static ChatResponse toolCallResponse() {
        AssistantMessage message = AssistantMessage.builder()
            .content("")
            .toolCalls(List.of(new AssistantMessage.ToolCall("call_1", "function", "getOrderStatus", "{}")))
            .build();
        return new ChatResponse(
            List.of(new Generation(message,
                ChatGenerationMetadata.builder().finishReason("tool_calls").build())),
            ChatResponseMetadata.builder().model("claude-sonnet-4-5").build());
    }

    private static ChatResponse textResponse(String text) {
        return new ChatResponse(
            List.of(new Generation(new AssistantMessage(text),
                ChatGenerationMetadata.builder().finishReason("stop").build())),
            ChatResponseMetadata.builder().model("claude-sonnet-4-5").build());
    }

    private List<EventData> conversationEvents(String eventName) {
        return otel.spans().stream()
            .filter(span -> span.getName().equals("support_conversation"))
            .map(SpanData::getEvents)
            .flatMap(List::stream)
            .filter(event -> event.getName().equals(eventName))
            .toList();
    }

    private LlmService service(JsonNode setup, ChatModel primary, ChatModel fallback) {
        return service(setup, primary, fallback, ToolCallingManager.builder().build());
    }

    private LlmService service(JsonNode setup, ChatModel primary, ChatModel fallback,
                               ToolCallingManager toolCallingManager) {
        AppConfig config = new AppConfig(
            setup.get("provider").asText(),
            setup.get("model").asText(),
            setup.get("model").asText(),
            setup.get("fallback_provider").asText(),
            setup.get("fallback_model").asText(),
            1024,
            0.7);
        Map<String, ChatModel> models = Map.of(
            "anthropicChatModel", primary,
            "openAiChatModel", fallback);
        return new LlmService(models, config, new Pricing(), conversations,
            toolCallingManager, otel.telemetry());
    }

    private LlmService sameTargetService(ChatModel model) {
        AppConfig config = new AppConfig(
            "ollama", "qwen3.5:9B", "qwen3.5:9B", "ollama", "qwen3.5:9B", 1024, 0.7);
        return new LlmService(Map.of("ollamaChatModel", model), config, new Pricing(), conversations,
            ToolCallingManager.builder().build(), otel.telemetry());
    }

    private static JsonNode fallbackSetup(JsonNode setup) {
        return ((com.fasterxml.jackson.databind.node.ObjectNode) setup.deepCopy())
            .put("provider", setup.get("primary_provider").asText())
            .put("model", setup.get("primary_model").asText());
    }

    private static long expectedMetricValue(JsonNode vector, String metricName) {
        for (JsonNode expected : vector.get("expected_metrics")) {
            if (expected.get("name").asText().equals(metricName) && expected.has("value")) {
                return expected.get("value").asLong();
            }
        }
        throw new AssertionError("Vector has no expected value for " + metricName);
    }

    private static ChatResponse chatResponse(JsonNode mock) {
        Generation generation = new Generation(
            new AssistantMessage(mock.get("content").asText()),
            ChatGenerationMetadata.builder().finishReason(mock.get("finish_reason").asText()).build());
        return new ChatResponse(List.of(generation), ChatResponseMetadata.builder()
            .id(mock.get("response_id").asText())
            .model(mock.get("model").asText())
            .usage(new DefaultUsage(mock.get("input_tokens").asInt(), mock.get("output_tokens").asInt()))
            .build());
    }

    private Optional<MetricData> metric(String name) {
        return otel.metrics().stream().filter(metric -> metric.getName().equals(name)).findFirst();
    }

    private LongPointData onlyLongPoint(String name) {
        MetricData metric = metric(name).orElseThrow(() -> new AssertionError(name + " was not recorded"));
        var points = metric.getLongSumData().getPoints();
        assertEquals(1, points.size(), name + " should have one attribute set");
        return points.iterator().next();
    }

    private long sum(String name) {
        MetricData metric = metric(name).orElseThrow(() -> new AssertionError(name + " was not recorded"));
        return metric.getLongSumData().getPoints().stream().mapToLong(LongPointData::getValue).sum();
    }
}
