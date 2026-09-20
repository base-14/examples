package com.example.support.pipeline;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import com.example.support.model.EscalationDecision;
import com.example.support.model.EscalationDecision.EscalationPriority;
import com.example.support.model.IntentResult;
import com.example.support.model.IntentResult.Intent;
import com.example.support.telemetry.GenAi;
import com.example.support.telemetry.Telemetry;

import io.opentelemetry.api.common.Attributes;
import io.opentelemetry.api.common.AttributesBuilder;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.context.Scope;

/** Decides whether a conversation needs a human agent. */
@Component
public class EscalationRouter {

    private static final Logger log = LoggerFactory.getLogger(EscalationRouter.class);
    private static final String EVALUATION_NAME = "escalation_check";

    private final Telemetry telemetry;

    public EscalationRouter(Telemetry telemetry) {
        this.telemetry = telemetry;
    }

    public EscalationDecision evaluate(IntentResult intent, int conversationTurns, int toolErrors) {
        Span span = telemetry.tracer().spanBuilder("escalation_check")
            .setAttribute("base14.support.stage", "route")
            .setAttribute("base14.support.conversation_turns", (long) conversationTurns)
            .startSpan();

        try (Scope ignored = span.makeCurrent()) {
            EscalationDecision decision = checkTriggers(intent, conversationTurns, toolErrors);

            span.setAttribute("base14.support.should_escalate", decision.shouldEscalate());
            if (decision.shouldEscalate()) {
                span.setAttribute("base14.support.escalation_reason", decision.reason());
                span.setAttribute("base14.support.escalation_priority", decision.priority().name());
                log.info("Escalation triggered: reason={} priority={}", decision.reason(), decision.priority());
            }
            span.addEvent(GenAi.EVALUATION_RESULT_EVENT, evaluationAttributes(intent, decision));

            return decision;

        } finally {
            span.end();
        }
    }

    private static Attributes evaluationAttributes(IntentResult intent, EscalationDecision decision) {
        AttributesBuilder attributes = Attributes.builder()
            .put(GenAi.EVALUATION_NAME, EVALUATION_NAME)
            .put(GenAi.EVALUATION_SCORE_VALUE, intent.confidence())
            .put(GenAi.EVALUATION_SCORE_LABEL, decision.shouldEscalate() ? "escalate" : "handled");
        if (decision.shouldEscalate()) {
            attributes.put(GenAi.EVALUATION_EXPLANATION, decision.summary());
        }
        return attributes.build();
    }

    EscalationDecision checkTriggers(IntentResult intent, int conversationTurns, int toolErrors) {
        if (intent.intent() == Intent.ESCALATE) {
            return EscalationDecision.escalate(
                "explicit_request", EscalationPriority.HIGH,
                "Customer explicitly requested human agent");
        }

        if (intent.intent() == Intent.COMPLAINT && intent.confidence() < 0.6) {
            return EscalationDecision.escalate(
                "low_confidence_complaint", EscalationPriority.HIGH,
                "Complaint with low classification confidence");
        }

        if (toolErrors >= 2) {
            return EscalationDecision.escalate(
                "tool_errors", EscalationPriority.MEDIUM,
                "Multiple tool call failures (" + toolErrors + ")");
        }

        if (intent.confidence() < 0.5) {
            return EscalationDecision.escalate(
                "low_confidence", EscalationPriority.LOW,
                "Low intent classification confidence");
        }

        if (conversationTurns > 5) {
            return EscalationDecision.escalate(
                "long_conversation", EscalationPriority.LOW,
                "Conversation exceeds 5 turns without resolution");
        }

        return EscalationDecision.noEscalation();
    }
}
