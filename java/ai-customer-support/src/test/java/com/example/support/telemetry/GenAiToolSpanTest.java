package com.example.support.telemetry;

import java.util.List;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.tracing.Tracer;
import io.micrometer.tracing.otel.bridge.OtelCurrentTraceContext;
import io.micrometer.tracing.otel.bridge.OtelTracer;
import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.sdk.trace.data.SpanData;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import org.springframework.ai.tool.definition.ToolDefinition;
import org.springframework.ai.tool.observation.ToolCallingObservationContext;
import org.springframework.ai.tool.observation.ToolCallingObservationDocumentation;

import com.example.support.filter.PiiFilter;
import com.example.support.llm.Pricing;
import com.example.support.llm.Providers;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** Drives Spring AI's tool observation through the handler and checks the execute_tool span. */
class GenAiToolSpanTest {

    private static final String ARGUMENTS = "{\"email\":\"jane@example.com\",\"orderId\":\"ORD-10001\"}";
    private static final String RESULT = "{\"orderId\":\"ORD-10001\",\"status\":\"SHIPPED\"}";

    private final TestOtel otel = new TestOtel();

    @AfterEach
    void tearDown() {
        otel.close();
    }

    @Test
    void toolArgumentsAndResultAreAbsentByDefault() {
        SpanData span = runToolObservation(false, RESULT);

        assertEquals("getOrderStatus", string(span, "gen_ai.tool.name"));
        assertNull(string(span, "gen_ai.tool.call.arguments"));
        assertNull(string(span, "gen_ai.tool.call.result"));
    }

    @Test
    void toolArgumentsAndResultAreScrubbedWhenCaptureIsOn() {
        SpanData span = runToolObservation(true, RESULT);

        String arguments = string(span, "gen_ai.tool.call.arguments");
        assertTrue(arguments.contains("ORD-10001"));
        assertTrue(!arguments.contains("jane@example.com"), "email must be redacted: " + arguments);
        assertEquals(RESULT, string(span, "gen_ai.tool.call.result"));
    }

    @Test
    void aLongToolResultIsTruncated() {
        SpanData span = runToolObservation(true, "x".repeat(5000));

        assertEquals(2000, string(span, "gen_ai.tool.call.result").length());
    }

    private SpanData runToolObservation(boolean captureContent, String result) {
        ToolCallingObservationContext context = ToolCallingObservationContext.builder()
            .toolDefinition(ToolDefinition.builder()
                .name("getOrderStatus")
                .description("Look up order status")
                .inputSchema("{}")
                .build())
            .toolCallId("call_1")
            .toolCallArguments(ARGUMENTS)
            .build();

        Observation observation = ToolCallingObservationDocumentation.TOOL_CALL
            .observation(new GenAiToolObservationConvention(), new GenAiToolObservationConvention(),
                () -> context, registryWith(handler(captureContent)))
            .start();
        context.setToolCallResult(result);
        observation.stop();

        List<SpanData> spans = otel.spans();
        assertEquals(1, spans.size());
        return spans.getFirst();
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

    private static ObservationRegistry registryWith(GenAiTracingObservationHandler handler) {
        ObservationRegistry registry = ObservationRegistry.create();
        registry.observationConfig().observationHandler(handler);
        return registry;
    }

    private static String string(SpanData span, String key) {
        return span.getAttributes().get(AttributeKey.stringKey(key));
    }
}
