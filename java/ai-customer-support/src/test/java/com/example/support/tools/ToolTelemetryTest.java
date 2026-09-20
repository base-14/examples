package com.example.support.tools;

import java.util.Map;

import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.context.Scope;
import io.opentelemetry.sdk.trace.data.EventData;
import io.opentelemetry.sdk.trace.data.SpanData;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import com.example.support.telemetry.ConversationScope;
import com.example.support.telemetry.GenAi;
import com.example.support.telemetry.SupportMetrics;
import com.example.support.telemetry.TestOtel;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * A failing tool marks the framework's execute_tool span and tells the conversation.
 */
class ToolTelemetryTest {

    private static final String CONVERSATION_ID = "conv-1";

    private final TestOtel otel = new TestOtel();
    private final ConversationScope conversations = new ConversationScope();
    private final ToolTelemetry toolTelemetry =
        new ToolTelemetry(conversations, new SupportMetrics(otel.telemetry()));

    @AfterEach
    void tearDown() {
        conversations.end();
        otel.close();
    }

    @Test
    void failureMarksTheToolSpanAndTellsTheConversation() {
        Span conversation = otel.sdk().getTracer("test").spanBuilder("support_conversation").startSpan();
        conversations.begin(CONVERSATION_ID, conversation);

        Span toolSpan = otel.sdk().getTracer("test").spanBuilder("execute_tool getOrderStatus").startSpan();
        Map<String, Object> result;
        try (Scope ignored = toolSpan.makeCurrent()) {
            result = toolTelemetry.failure("getOrderStatus", "OrderNotFound", "Order ORD-99999 not found");
        } finally {
            toolSpan.end();
        }
        conversation.end();

        assertEquals(Map.of("error", "Order ORD-99999 not found"), result);

        SpanData tool = span("execute_tool getOrderStatus");
        assertEquals(StatusCode.ERROR, tool.getStatus().getStatusCode());
        assertEquals("OrderNotFound", tool.getAttributes().get(AttributeKey.stringKey(GenAi.ERROR_TYPE)));
        assertTrue(tool.getEvents().stream().anyMatch(event -> event.getName().equals("exception")),
            "the tool span records the exception");

        EventData failed = span("support_conversation").getEvents().stream()
            .filter(event -> event.getName().equals(GenAi.TOOL_FAILED_EVENT))
            .findFirst()
            .orElseThrow(() -> new AssertionError("tool_execution_failed was not recorded"));
        assertEquals("getOrderStatus", failed.getAttributes().get(AttributeKey.stringKey(GenAi.TOOL_NAME)));
        assertEquals("OrderNotFound", failed.getAttributes().get(AttributeKey.stringKey(GenAi.ERROR_TYPE)));
    }

    @Test
    void successLeavesTheToolSpanAlone() {
        Span toolSpan = otel.sdk().getTracer("test").spanBuilder("execute_tool getProductInfo").startSpan();
        try (Scope ignored = toolSpan.makeCurrent()) {
            toolTelemetry.success("getProductInfo");
        } finally {
            toolSpan.end();
        }

        SpanData tool = span("execute_tool getProductInfo");
        assertEquals(StatusCode.UNSET, tool.getStatus().getStatusCode());
        assertTrue(tool.getEvents().isEmpty());
    }

    private SpanData span(String name) {
        return otel.spans().stream()
            .filter(candidate -> candidate.getName().equals(name))
            .findFirst()
            .orElseThrow(() -> new AssertionError("no span named " + name));
    }
}
