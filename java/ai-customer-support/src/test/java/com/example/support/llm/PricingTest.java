package com.example.support.llm;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class PricingTest {

    @Test
    void calculateCostUnknownModelUsesFallback() {
        var pricing = new Pricing();
        // No pricing loaded = all models unknown = fallback rates ($3.0 input, $15.0 output)
        double cost = pricing.calculateCost("unknown-model", 1000, 500);
        // (1000 * 3.0 + 500 * 15.0) / 1_000_000 = (3000 + 7500) / 1_000_000 = 0.0105
        assertEquals(0.0105, cost, 0.0001);
    }

    @Test
    void hasModelReturnsFalseWhenNotLoaded() {
        var pricing = new Pricing();
        assertFalse(pricing.hasModel("gpt-4.1"));
    }
}
