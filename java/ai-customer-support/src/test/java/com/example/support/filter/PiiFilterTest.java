package com.example.support.filter;

import java.util.stream.Stream;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.junit.jupiter.params.provider.NullAndEmptySource;

import static org.junit.jupiter.api.Assertions.*;

class PiiFilterTest {

    private final PiiFilter filter = new PiiFilter();

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
}
