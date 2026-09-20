package com.example.support.tools;

import java.util.Map;

import org.springframework.stereotype.Component;

import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.api.common.Attributes;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.StatusCode;

import com.example.support.telemetry.ConversationScope;
import com.example.support.telemetry.GenAi;
import com.example.support.telemetry.SupportMetrics;

/**
 * Outcome recording for {@code @Tool} methods. Spring AI's tool observation owns the
 * {@code execute_tool} span; this marks that span failed when the tool returns an
 * error result, and adds a {@code tool_execution_failed} event to the conversation.
 */
@Component
public class ToolTelemetry {

    private final ConversationScope conversations;
    private final SupportMetrics metrics;

    public ToolTelemetry(ConversationScope conversations, SupportMetrics metrics) {
        this.conversations = conversations;
        this.metrics = metrics;
    }

    public void success(String toolName) {
        metrics.recordToolCall(toolName, true);
    }

    public Map<String, Object> failure(String toolName, String errorType, String message) {
        ToolFailedException error = new ToolFailedException(message);
        Span span = Span.current();
        span.recordException(error);
        span.setAttribute(GenAi.ERROR_TYPE, errorType);
        span.setStatus(StatusCode.ERROR, message);

        conversations.recordOnConversation(GenAi.TOOL_FAILED_EVENT, Attributes.of(
            AttributeKey.stringKey(GenAi.TOOL_NAME), toolName,
            AttributeKey.stringKey(GenAi.ERROR_TYPE), errorType));
        metrics.recordToolCall(toolName, false);

        return Map.of("error", message);
    }
}
