package com.example.support.pipeline;

import java.util.List;
import java.util.stream.Stream;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

import com.example.support.llm.LlmResponse;
import com.example.support.model.IntentResult;
import com.example.support.model.IntentResult.Intent;

import static org.junit.jupiter.api.Assertions.*;

class IntentClassifierTest {

    private final IntentClassifier classifier = new IntentClassifier(null);

    static Stream<Arguments> intentParsingCases() {
        return Stream.of(
            Arguments.of(
                """
                {"intent": "QUERY", "confidence": 0.95, "sub_category": "order_status", "entities": ["ORD-12345"]}
                """,
                Intent.QUERY, 0.95, "order_status", List.of("ORD-12345")
            ),
            Arguments.of(
                """
                {"intent": "ACTION", "confidence": 0.88, "sub_category": "return_request", "entities": ["ORD-99001", "headphones"]}
                """,
                Intent.ACTION, 0.88, "return_request", List.of("ORD-99001", "headphones")
            ),
            Arguments.of(
                """
                {"intent": "COMPLAINT", "confidence": 0.72, "sub_category": "delivery_delay", "entities": []}
                """,
                Intent.COMPLAINT, 0.72, "delivery_delay", List.of()
            ),
            Arguments.of(
                """
                {"intent": "ESCALATE", "confidence": 0.99, "sub_category": "human_agent_request", "entities": []}
                """,
                Intent.ESCALATE, 0.99, "human_agent_request", List.of()
            )
        );
    }

    @ParameterizedTest
    @MethodSource("intentParsingCases")
    void parsesIntentResponse(String json, Intent expectedIntent, double expectedConfidence,
                              String expectedSub, List<String> expectedEntities) {
        var response = new LlmResponse(json, "gpt-4.1-mini", "openai", 50, 30, 0.001, "stop");
        IntentResult result = classifier.parseResponse(response);

        assertEquals(expectedIntent, result.intent());
        assertEquals(expectedConfidence, result.confidence(), 0.01);
        assertEquals(expectedSub, result.subCategory());
        assertEquals(expectedEntities, result.entities());
        assertEquals(50, result.inputTokens());
        assertEquals(30, result.outputTokens());
    }

    @Test
    void parsesMarkdownWrappedJson() {
        String json = """
            ```json
            {"intent": "QUERY", "confidence": 0.8, "sub_category": "product_info", "entities": ["laptop"]}
            ```
            """;
        var response = new LlmResponse(json, "gpt-4.1-mini", "openai", 40, 25, 0.001, "stop");
        IntentResult result = classifier.parseResponse(response);

        assertEquals(Intent.QUERY, result.intent());
        assertEquals(0.8, result.confidence(), 0.01);
        assertEquals("product_info", result.subCategory());
        assertEquals(List.of("laptop"), result.entities());
    }

    @Test
    void fallsBackOnInvalidJson() {
        var response = new LlmResponse("not json", "gpt-4.1-mini", "openai", 30, 10, 0.001, "stop");
        IntentResult result = classifier.parseResponse(response);

        assertEquals(Intent.QUERY, result.intent());
        assertEquals(0.3, result.confidence(), 0.01);
        assertEquals("parse_error", result.subCategory());
    }

    @Test
    void fallbackResult() {
        IntentResult result = IntentResult.fallback();
        assertEquals(Intent.QUERY, result.intent());
        assertEquals(0.0, result.confidence());
        assertEquals("unknown", result.subCategory());
        assertTrue(result.entities().isEmpty());
    }
}
