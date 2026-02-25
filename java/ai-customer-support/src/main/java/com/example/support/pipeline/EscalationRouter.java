package com.example.support.pipeline;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import com.example.support.model.EscalationDecision;
import com.example.support.model.EscalationDecision.EscalationPriority;
import com.example.support.model.IntentResult;
import com.example.support.model.IntentResult.Intent;

import io.opentelemetry.api.GlobalOpenTelemetry;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;

@Component
public class EscalationRouter {

    private static final Logger log = LoggerFactory.getLogger(EscalationRouter.class);

    private final Tracer tracer;

    public EscalationRouter() {
        this.tracer = GlobalOpenTelemetry.getTracer("ai-customer-support");
    }

    public EscalationDecision evaluate(IntentResult intent, int conversationTurns, int toolErrors) {
        Span span = tracer.spanBuilder("escalation_check")
            .setAttribute("support.stage", "route")
            .setAttribute("support.conversation_turns", (long) conversationTurns)
            .startSpan();

        try (Scope ignored = span.makeCurrent()) {
            EscalationDecision decision = checkTriggers(intent, conversationTurns, toolErrors);

            span.setAttribute("support.should_escalate", decision.shouldEscalate());
            if (decision.shouldEscalate()) {
                span.setAttribute("support.escalation_reason", decision.reason());
                span.setAttribute("support.escalation_priority", decision.priority().name());
                log.info("Escalation triggered: reason={} priority={}", decision.reason(), decision.priority());
            }

            return decision;

        } finally {
            span.end();
        }
    }

    EscalationDecision checkTriggers(IntentResult intent, int conversationTurns, int toolErrors) {
        // Explicit ESCALATE intent — immediate
        if (intent.intent() == Intent.ESCALATE) {
            return EscalationDecision.escalate(
                "explicit_request", EscalationPriority.HIGH,
                "Customer explicitly requested human agent");
        }

        // Complaint + low confidence (< 0.6) — auto-escalate
        if (intent.intent() == Intent.COMPLAINT && intent.confidence() < 0.6) {
            return EscalationDecision.escalate(
                "low_confidence_complaint", EscalationPriority.HIGH,
                "Complaint with low classification confidence");
        }

        // 2+ tool errors — escalate with context
        if (toolErrors >= 2) {
            return EscalationDecision.escalate(
                "tool_errors", EscalationPriority.MEDIUM,
                "Multiple tool call failures (" + toolErrors + ")");
        }

        // Low intent confidence (< 0.5) — offer human agent
        if (intent.confidence() < 0.5) {
            return EscalationDecision.escalate(
                "low_confidence", EscalationPriority.LOW,
                "Low intent classification confidence");
        }

        // > 5 turns without resolution — suggest escalation
        if (conversationTurns > 5) {
            return EscalationDecision.escalate(
                "long_conversation", EscalationPriority.LOW,
                "Conversation exceeds 5 turns without resolution");
        }

        return EscalationDecision.noEscalation();
    }
}
