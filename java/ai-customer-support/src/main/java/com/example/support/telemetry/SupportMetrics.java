package com.example.support.telemetry;

import org.springframework.stereotype.Component;

import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.api.common.Attributes;
import io.opentelemetry.api.metrics.DoubleHistogram;
import io.opentelemetry.api.metrics.LongCounter;
import io.opentelemetry.api.metrics.Meter;

@Component
public class SupportMetrics {

    private final DoubleHistogram conversationDuration;
    private final DoubleHistogram conversationTurns;
    private final LongCounter escalationCount;
    private final LongCounter toolCallCount;
    private final DoubleHistogram ragSimilarity;

    public SupportMetrics(Telemetry telemetry) {
        Meter meter = telemetry.meter();

        this.conversationDuration = meter.histogramBuilder("base14.support.conversation.duration")
            .setUnit("s")
            .setDescription("Duration of customer support conversations")
            .build();

        this.conversationTurns = meter.histogramBuilder("base14.support.conversation.turns")
            .setUnit("{turn}")
            .setDescription("Number of turns in customer support conversations")
            .build();

        this.escalationCount = meter.counterBuilder("base14.support.escalation.count")
            .setDescription("Number of escalated conversations")
            .build();

        this.toolCallCount = meter.counterBuilder("base14.support.tool_calls")
            .setDescription("Number of tool calls made")
            .build();

        this.ragSimilarity = meter.histogramBuilder("base14.support.rag.similarity")
            .setDescription("Top similarity score from RAG retrieval")
            .build();
    }

    public void recordConversationDuration(double seconds, String intent, boolean escalated) {
        conversationDuration.record(seconds, Attributes.of(
            AttributeKey.stringKey("base14.support.intent"), intent,
            AttributeKey.booleanKey("base14.support.escalated"), escalated
        ));
    }

    public void recordConversationTurns(int turns, String intent, boolean resolved) {
        conversationTurns.record(turns, Attributes.of(
            AttributeKey.stringKey("base14.support.intent"), intent,
            AttributeKey.booleanKey("base14.support.resolved"), resolved
        ));
    }

    public void recordEscalation(String reason, String priority) {
        escalationCount.add(1, Attributes.of(
            AttributeKey.stringKey("base14.support.escalation_reason"), reason,
            AttributeKey.stringKey("base14.support.escalation_priority"), priority
        ));
    }

    public void recordToolCall(String toolName, boolean success) {
        toolCallCount.add(1, Attributes.of(
            AttributeKey.stringKey("base14.support.tool_name"), toolName,
            AttributeKey.booleanKey("base14.support.tool_success"), success
        ));
    }

    public void recordRagSimilarity(double similarity, String intent) {
        ragSimilarity.record(similarity, Attributes.of(
            AttributeKey.stringKey("base14.support.intent"), intent
        ));
    }
}
