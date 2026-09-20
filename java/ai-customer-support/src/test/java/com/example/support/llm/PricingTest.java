package com.example.support.llm;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PricingTest {

    private final Pricing pricing = new Pricing();

    @Test
    void unknownModelCostsNothing() {
        assertEquals(0.0, pricing.calculateCost("no-such-model", 1000, 500));
    }

    @Test
    void knownModelUsesTheFileRates() {
        // claude-sonnet-4 is $3.00 per million input, $15.00 per million output.
        assertEquals(0.000111, pricing.calculateCost("claude-sonnet-4", 12, 5), 1e-9);
    }

    @ParameterizedTest
    @CsvSource({
        "claude-sonnet-4-20250514, claude-sonnet-4",
        "claude-haiku-4-5-20251001, claude-haiku-4.5",
        "gpt-4.1-2025-04-14,        gpt-4.1",
        "gemini-3.5-flash,          gemini-3.5-flash",
    })
    void normalisesDatedAndDashMinorIds(String modelId, String expected) {
        assertEquals(expected, Pricing.normalizeModel(modelId));
    }

    @Test
    void datedIdPricesAsItsCanonicalKey() {
        assertEquals(
            pricing.calculateCost("claude-sonnet-4", 12, 5),
            pricing.calculateCost("claude-sonnet-4-20250514", 12, 5));
    }

    @Test
    void hasModelFollowsNormalisation() {
        assertTrue(pricing.hasModel("claude-haiku-4-5-20251001"));
        assertFalse(pricing.hasModel("no-such-model"));
    }
}
