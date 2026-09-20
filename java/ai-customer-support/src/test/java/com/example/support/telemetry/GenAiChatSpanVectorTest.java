package com.example.support.telemetry;

import java.util.List;

import com.fasterxml.jackson.databind.JsonNode;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.tracing.Tracer;
import io.micrometer.tracing.handler.DefaultTracingObservationHandler;
import io.micrometer.tracing.otel.bridge.OtelCurrentTraceContext;
import io.micrometer.tracing.otel.bridge.OtelTracer;
import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.sdk.metrics.data.MetricData;
import io.opentelemetry.sdk.trace.data.EventData;
import io.opentelemetry.sdk.trace.data.SpanData;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import org.springframework.ai.chat.messages.AssistantMessage;
import org.springframework.ai.chat.messages.Message;
import org.springframework.ai.chat.messages.SystemMessage;
import org.springframework.ai.chat.messages.UserMessage;
import org.springframework.ai.chat.metadata.ChatGenerationMetadata;
import org.springframework.ai.chat.metadata.ChatResponseMetadata;
import org.springframework.ai.chat.metadata.DefaultUsage;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.ai.chat.model.Generation;
import org.springframework.ai.chat.observation.ChatModelObservationContext;
import org.springframework.ai.chat.observation.ChatModelObservationDocumentation;
import org.springframework.ai.chat.observation.DefaultChatModelObservationConvention;
import org.springframework.ai.chat.prompt.ChatOptions;
import org.springframework.ai.chat.prompt.Prompt;

import com.example.support.filter.PiiFilter;
import com.example.support.llm.Pricing;
import com.example.support.llm.Providers;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Drives Spring AI's chat observation with a stubbed response and asserts the span the
 * SDK exports against {@code _shared/test-vectors/chat-completion.json}.
 */
class GenAiChatSpanVectorTest {

    private static final JsonNode VECTOR = TestVectors.load("chat-completion.json");

    private final TestOtel otel = new TestOtel();

    @AfterEach
    void tearDown() {
        otel.close();
    }

    @Test
    void chatCompletionMatchesTheVector() {
        runObservation(false);

        JsonNode expected = VECTOR.get("expected_span");
        JsonNode attrs = expected.get("attributes");
        SpanData span = onlySpan();

        assertEquals(expected.get("name").asText(), span.getName());
        assertEquals(SpanKind.CLIENT, span.getKind());
        assertEquals(attrs.get("gen_ai.operation.name").asText(), string(span, "gen_ai.operation.name"));
        assertEquals(attrs.get("gen_ai.provider.name").asText(), string(span, "gen_ai.provider.name"));
        assertEquals(attrs.get("gen_ai.request.model").asText(), string(span, "gen_ai.request.model"));
        assertEquals(attrs.get("gen_ai.response.model").asText(), string(span, "gen_ai.response.model"));
        assertEquals(attrs.get("gen_ai.response.id").asText(), string(span, "gen_ai.response.id"));
        assertEquals(String.valueOf(attrs.get("gen_ai.request.temperature").asDouble()),
            string(span, "gen_ai.request.temperature"));
        assertEquals(String.valueOf(attrs.get("gen_ai.request.max_tokens").asInt()),
            string(span, "gen_ai.request.max_tokens"));
        assertEquals(attrs.get("server.address").asText(), string(span, "server.address"));
        assertEquals(attrs.get("server.port").asLong(),
            span.getAttributes().get(AttributeKey.longKey("server.port")));
        assertEquals(attrs.get("gen_ai.usage.input_tokens").asLong(),
            span.getAttributes().get(AttributeKey.longKey("gen_ai.usage.input_tokens")));
        assertEquals(attrs.get("gen_ai.usage.output_tokens").asLong(),
            span.getAttributes().get(AttributeKey.longKey("gen_ai.usage.output_tokens")));
        assertEquals(List.of(attrs.get("gen_ai.response.finish_reasons").get(0).asText()),
            span.getAttributes().get(AttributeKey.stringArrayKey("gen_ai.response.finish_reasons")));
        assertEquals(attrs.get("base14.gen_ai.cost_usd").asDouble(),
            span.getAttributes().get(AttributeKey.doubleKey("base14.gen_ai.cost_usd")), 1e-9);

        assertNotNull(span.getAttributes().get(AttributeKey.stringKey("gen_ai.agent.name")));
        assertFalse(span.getAttributes().asMap().keySet().stream()
            .anyMatch(key -> key.getKey().equals("gen_ai.system")));
    }

    @Test
    void costCounterMatchesTheVector() {
        runObservation(false);

        MetricData cost = otel.metrics().stream()
            .filter(metric -> metric.getName().equals("base14.gen_ai.cost"))
            .findFirst()
            .orElseThrow(() -> new AssertionError("base14.gen_ai.cost was not recorded"));

        double recorded = cost.getDoubleSumData().getPoints().iterator().next().getValue();
        assertEquals(VECTOR.get("expected_span").get("attributes").get("base14.gen_ai.cost_usd").asDouble(),
            recorded, 1e-9);
    }

    @Test
    void contentEventIsAbsentByDefault() {
        runObservation(false);
        assertTrue(onlySpan().getEvents().isEmpty());
    }

    @Test
    void contentEventCarriesScrubbedMessagesWhenCaptureIsOn() {
        runObservation(true);

        List<EventData> events = onlySpan().getEvents();
        assertEquals(1, events.size());
        EventData event = events.getFirst();
        assertEquals("gen_ai.client.inference.operation.details", event.getName());
        assertEquals(VECTOR.get("input").get("prompt").asText(),
            event.getAttributes().get(AttributeKey.stringKey("gen_ai.input.messages")));
        assertEquals(VECTOR.get("input").get("system").asText(),
            event.getAttributes().get(AttributeKey.stringKey("gen_ai.system_instructions")));
        assertEquals(VECTOR.get("mock_response").get("content").asText(),
            event.getAttributes().get(AttributeKey.stringKey("gen_ai.output.messages")));
    }

    @Test
    void theContentEventOnAFailedCallCarriesInputsAndNoOutput() {
        runObservation(registryWith(handler(true)), new RuntimeException("Service unavailable"));

        EventData event = onlySpan().getEvents().stream()
            .filter(candidate -> candidate.getName().equals("gen_ai.client.inference.operation.details"))
            .findFirst()
            .orElseThrow(() -> new AssertionError("no inference details event on the failed call"));
        assertEquals(VECTOR.get("input").get("prompt").asText(),
            event.getAttributes().get(AttributeKey.stringKey("gen_ai.input.messages")));
        assertEquals(VECTOR.get("input").get("system").asText(),
            event.getAttributes().get(AttributeKey.stringKey("gen_ai.system_instructions")));
        assertNull(event.getAttributes().get(AttributeKey.stringKey("gen_ai.output.messages")));
    }

    @Test
    void bootsDefaultTracingHandlerDoesNotOpenASecondSpan() {
        // Boot puts tracing handlers in a first-matching composite. This handler is ordered
        // first, so it claims the chat context and the default handler never sees it.
        ObservationRegistry registry = registryWith(
            new ObservationHandler.FirstMatchingCompositeObservationHandler(
                handler(false),
                new DefaultTracingObservationHandler(micrometerTracer())));

        runObservation(registry, null);

        assertEquals(1, otel.spans().size(), "exactly one chat span per LLM call");
        assertEquals(SpanKind.CLIENT, otel.spans().getFirst().getKind());
    }

    @Test
    void aFailedCallIsErrorAndTheNextOneIsNot() {
        ObservationRegistry registry = registryWith(handler(false));

        runObservation(registry, new RuntimeException("Service unavailable"));
        runObservation(registry, null);

        List<SpanData> spans = otel.spans();
        assertEquals(2, spans.size());

        SpanData failed = spans.getFirst();
        assertEquals(StatusCode.ERROR, failed.getStatus().getStatusCode());
        assertEquals("RuntimeException", string(failed, "error.type"));

        SpanData succeeded = spans.get(1);
        assertEquals(StatusCode.OK, succeeded.getStatus().getStatusCode());
        assertNull(succeeded.getAttributes().get(AttributeKey.stringKey("error.type")));
    }

    private void runObservation(boolean captureContent) {
        runObservation(registryWith(handler(captureContent)), null);
    }

    private void runObservation(ObservationRegistry registry, Throwable error) {
        JsonNode input = VECTOR.get("input");
        JsonNode mock = VECTOR.get("mock_response");

        List<Message> messages = List.of(
            new SystemMessage(input.get("system").asText()),
            new UserMessage(input.get("prompt").asText()));
        Prompt prompt = new Prompt(messages, ChatOptions.builder()
            .model(input.get("model").asText())
            .temperature(input.get("temperature").asDouble())
            .maxTokens(input.get("max_tokens").asInt())
            .build());

        ChatModelObservationContext context = ChatModelObservationContext.builder()
            .prompt(prompt)
            .provider(input.get("provider").asText())
            .build();

        Observation observation = ChatModelObservationDocumentation.CHAT_MODEL_OPERATION
            .observation(new GenAiChatObservationConvention(), new DefaultChatModelObservationConvention(),
                () -> context, registry)
            .start();
        if (error != null) {
            observation.error(error);
        } else {
            context.setResponse(chatResponse(mock));
        }
        observation.stop();
    }

    private GenAiTracingObservationHandler handler(boolean captureContent) {
        return new GenAiTracingObservationHandler(
            micrometerTracer(),
            otel.telemetry(),
            new Pricing(),
            new Providers("http://localhost:11434"),
            new ConversationScope(),
            new PiiFilter(),
            captureContent);
    }

    private Tracer micrometerTracer() {
        return new OtelTracer(otel.sdk().getTracer("test"), new OtelCurrentTraceContext(), event -> { });
    }

    private static ObservationRegistry registryWith(ObservationHandler<?>... handlers) {
        ObservationRegistry registry = ObservationRegistry.create();
        for (ObservationHandler<?> handler : handlers) {
            registry.observationConfig().observationHandler(handler);
        }
        return registry;
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

    private SpanData onlySpan() {
        List<SpanData> spans = otel.spans();
        assertEquals(1, spans.size(), "exactly one chat span per LLM call");
        return spans.getFirst();
    }

    private static String string(SpanData span, String key) {
        return span.getAttributes().get(AttributeKey.stringKey(key));
    }
}
