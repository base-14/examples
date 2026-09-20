package com.example.support.filter;

import java.util.stream.Stream;

import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.context.Scope;
import io.opentelemetry.sdk.trace.data.EventData;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.junit.jupiter.params.provider.NullAndEmptySource;

import com.example.support.telemetry.GenAi;
import com.example.support.telemetry.TestOtel;

import static org.junit.jupiter.api.Assertions.*;

class PiiFilterTest {

    private final PiiFilter filter = new PiiFilter();
    private final TestOtel otel = new TestOtel();

    @AfterEach
    void tearDown() {
        otel.close();
    }

    static Stream<Arguments> piiCases() {
        return Stream.of(
            // Email
            Arguments.of("Contact john@example.com for help",
                "Contact [REDACTED] for help"),
            Arguments.of("Emails: a@b.co and user.name+tag@domain.org",
                "Emails: [REDACTED] and [REDACTED]"),

            // SSN
            Arguments.of("SSN: 123-45-6789", "SSN: [REDACTED]"),
            Arguments.of("My social is 999-88-7777 please check",
                "My social is [REDACTED] please check"),

            // Credit card
            Arguments.of("Card: 4111-1111-1111-1111", "Card: [REDACTED]"),
            Arguments.of("Pay with 4111 1111 1111 1111", "Pay with [REDACTED]"),
            Arguments.of("Number 4111111111111111 on file", "Number [REDACTED] on file"),

            // Phone
            Arguments.of("Call 555-123-4567", "Call [REDACTED]"),
            Arguments.of("Phone: (555)123-4567", "Phone: [REDACTED]"),
            Arguments.of("Reach me at 5551234567", "Reach me at [REDACTED]"),

            // Multiple PII types
            Arguments.of("Email john@test.com, SSN 111-22-3333, card 4000-0000-0000-0000",
                "Email [REDACTED], SSN [REDACTED], card [REDACTED]")
        );
    }

    @ParameterizedTest
    @MethodSource("piiCases")
    void scrubsDetectedPii(String input, String expected) {
        assertEquals(expected, filter.scrub(input));
    }

    @ParameterizedTest
    @NullAndEmptySource
    void handlesNullAndEmpty(String input) {
        assertEquals(input, filter.scrub(input));
    }

    @Test
    void leavesCleanTextUnchanged() {
        String clean = "Order ORD-12345 has been shipped. Tracking: TRK-ABC123";
        assertEquals(clean, filter.scrub(clean));
    }

    @Test
    void containsPiiDetectsEmail() {
        assertTrue(filter.containsPii("contact user@example.com"));
        assertFalse(filter.containsPii("no pii here"));
    }

    @Test
    void containsPiiDetectsSSN() {
        assertTrue(filter.containsPii("SSN 123-45-6789"));
    }

    @Test
    void containsPiiDetectsCreditCard() {
        assertTrue(filter.containsPii("4111111111111111"));
    }

    @Test
    void containsPiiDetectsPhone() {
        assertTrue(filter.containsPii("Call 555-123-4567"));
    }

    @Test
    void evaluateRecordsAFailedEvaluationAndRedacts() {
        String scrubbed = withSpan(() -> filter.evaluate("Email john@test.com, SSN 111-22-3333"));

        assertEquals("Email [REDACTED], SSN [REDACTED]", scrubbed);

        var attributes = evaluationEvent().getAttributes();
        assertEquals("pii_scan", attributes.get(AttributeKey.stringKey(GenAi.EVALUATION_NAME)));
        assertEquals(0.0, attributes.get(AttributeKey.doubleKey(GenAi.EVALUATION_SCORE_VALUE)));
        assertEquals("fail", attributes.get(AttributeKey.stringKey(GenAi.EVALUATION_SCORE_LABEL)));
        assertEquals("Redacted email, ssn",
            attributes.get(AttributeKey.stringKey(GenAi.EVALUATION_EXPLANATION)));
    }

    @Test
    void evaluateRecordsAPassingEvaluationForCleanText() {
        String clean = "Order ORD-12345 has been shipped";
        assertEquals(clean, withSpan(() -> filter.evaluate(clean)));

        var attributes = evaluationEvent().getAttributes();
        assertEquals(1.0, attributes.get(AttributeKey.doubleKey(GenAi.EVALUATION_SCORE_VALUE)));
        assertEquals("pass", attributes.get(AttributeKey.stringKey(GenAi.EVALUATION_SCORE_LABEL)));
        assertNull(attributes.get(AttributeKey.stringKey(GenAi.EVALUATION_EXPLANATION)));
    }

    private <T> T withSpan(java.util.function.Supplier<T> action) {
        Span span = otel.sdk().getTracer("test").spanBuilder("pipeline").startSpan();
        try (Scope ignored = span.makeCurrent()) {
            return action.get();
        } finally {
            span.end();
        }
    }

    private EventData evaluationEvent() {
        return otel.spans().getFirst().getEvents().stream()
            .filter(event -> event.getName().equals(GenAi.EVALUATION_RESULT_EVENT))
            .findFirst()
            .orElseThrow();
    }
}
