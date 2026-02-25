package com.example.support.pipeline;

import java.util.List;
import java.util.stream.Stream;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

import com.example.support.model.EscalationDecision;
import com.example.support.model.EscalationDecision.EscalationPriority;
import com.example.support.model.IntentResult;
import com.example.support.model.IntentResult.Intent;

import static org.junit.jupiter.api.Assertions.*;

class EscalationRouterTest {

    private final EscalationRouter router = new EscalationRouter();

    static IntentResult intent(Intent type, double confidence) {
        return new IntentResult(type, confidence, "test", List.of(), 0, 0);
    }

    static Stream<Arguments> escalationTriggers() {
        return Stream.of(
            // Explicit ESCALATE intent
            Arguments.of(intent(Intent.ESCALATE, 0.99), 1, 0,
                true, "explicit_request", EscalationPriority.HIGH),

            // Complaint + low confidence
            Arguments.of(intent(Intent.COMPLAINT, 0.5), 1, 0,
                true, "low_confidence_complaint", EscalationPriority.HIGH),

            // Complaint + low confidence (boundary)
            Arguments.of(intent(Intent.COMPLAINT, 0.59), 1, 0,
                true, "low_confidence_complaint", EscalationPriority.HIGH),

            // Complaint + adequate confidence — no escalation
            Arguments.of(intent(Intent.COMPLAINT, 0.6), 1, 0,
                false, "", EscalationPriority.LOW),

            // 2+ tool errors
            Arguments.of(intent(Intent.QUERY, 0.9), 1, 2,
                true, "tool_errors", EscalationPriority.MEDIUM),

            // Low overall confidence
            Arguments.of(intent(Intent.QUERY, 0.4), 1, 0,
                true, "low_confidence", EscalationPriority.LOW),

            // Confidence at boundary (0.5) — no escalation
            Arguments.of(intent(Intent.QUERY, 0.5), 1, 0,
                false, "", EscalationPriority.LOW),

            // Long conversation
            Arguments.of(intent(Intent.QUERY, 0.9), 6, 0,
                true, "long_conversation", EscalationPriority.LOW),

            // Long conversation boundary (5 turns) — no escalation
            Arguments.of(intent(Intent.QUERY, 0.9), 5, 0,
                false, "", EscalationPriority.LOW),

            // Normal — no escalation
            Arguments.of(intent(Intent.QUERY, 0.95), 2, 0,
                false, "", EscalationPriority.LOW),

            // ACTION with high confidence — no escalation
            Arguments.of(intent(Intent.ACTION, 0.85), 3, 0,
                false, "", EscalationPriority.LOW)
        );
    }

    @ParameterizedTest
    @MethodSource("escalationTriggers")
    void evaluatesTriggers(IntentResult intent, int turns, int toolErrors,
                           boolean shouldEscalate, String reason, EscalationPriority priority) {
        EscalationDecision decision = router.checkTriggers(intent, turns, toolErrors);

        assertEquals(shouldEscalate, decision.shouldEscalate());
        assertEquals(reason, decision.reason());
        assertEquals(priority, decision.priority());
    }

    @Test
    void escalatePriorityOrder_explicitOverridesOthers() {
        // ESCALATE intent should trigger even with other conditions
        var intent = new IntentResult(Intent.ESCALATE, 0.3, "test", List.of(), 0, 0);
        EscalationDecision decision = router.checkTriggers(intent, 10, 5);

        assertTrue(decision.shouldEscalate());
        assertEquals("explicit_request", decision.reason());
        assertEquals(EscalationPriority.HIGH, decision.priority());
    }

    @Test
    void noEscalationFactory() {
        var decision = EscalationDecision.noEscalation();
        assertFalse(decision.shouldEscalate());
        assertEquals("", decision.reason());
    }
}
