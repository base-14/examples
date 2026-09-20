package com.example.support.telemetry;

import io.opentelemetry.api.common.Attributes;
import io.opentelemetry.api.trace.Span;

import org.springframework.stereotype.Component;

/**
 * The conversation a pipeline run belongs to, for the duration of that run. Spans the
 * framework creates read the conversation id from here, and non-fatal failures add
 * their event to the conversation span.
 */
@Component
public class ConversationScope {

    public static final String AGENT_NAME = "customer-support-agent";

    public record Conversation(String id, Span span) {}

    private final ThreadLocal<Conversation> current = new ThreadLocal<>();

    public void begin(String conversationId, Span span) {
        current.set(new Conversation(conversationId, span));
    }

    public void end() {
        current.remove();
    }

    public Conversation current() {
        return current.get();
    }

    public String conversationId() {
        Conversation conversation = current.get();
        return conversation != null ? conversation.id() : "";
    }

    public void recordOnConversation(String eventName, Attributes attributes) {
        Conversation conversation = current.get();
        Span span = conversation != null ? conversation.span() : Span.current();
        span.addEvent(eventName, attributes);
    }
}
