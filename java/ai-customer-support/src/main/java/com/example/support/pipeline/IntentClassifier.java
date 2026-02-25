package com.example.support.pipeline;

import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import com.example.support.llm.LlmResponse;
import com.example.support.llm.LlmService;
import com.example.support.model.IntentResult;
import com.example.support.model.IntentResult.Intent;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import io.opentelemetry.api.GlobalOpenTelemetry;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;

@Component
public class IntentClassifier {

    private static final Logger log = LoggerFactory.getLogger(IntentClassifier.class);
    private static final ObjectMapper mapper = new ObjectMapper();

    private static final String SYSTEM_PROMPT = """
        You are a customer support intent classifier. Classify the customer's message into exactly one intent.

        Respond ONLY with a JSON object (no markdown, no explanation):
        {
          "intent": "QUERY|ACTION|COMPLAINT|ESCALATE",
          "confidence": 0.0-1.0,
          "sub_category": "brief category description",
          "entities": ["extracted entity 1", "extracted entity 2"]
        }

        Intent definitions:
        - QUERY: Information request (order status, product info, policy questions)
        - ACTION: Request to perform an action (initiate return, cancel order, update account)
        - COMPLAINT: Expression of dissatisfaction or problem report
        - ESCALATE: Explicit request to speak with a human agent

        Extract relevant entities like order IDs (ORD-xxxxx), product names, return IDs (RET-xxxxx), dates.
        """;

    private final LlmService llmService;
    private final Tracer tracer;

    public IntentClassifier(LlmService llmService) {
        this.llmService = llmService;
        this.tracer = GlobalOpenTelemetry.getTracer("ai-customer-support");
    }

    public IntentResult classify(String userMessage) {
        Span span = tracer.spanBuilder("classify_intent")
            .setAttribute("support.stage", "classify")
            .startSpan();

        try (Scope ignored = span.makeCurrent()) {
            LlmResponse response = llmService.generateFast(SYSTEM_PROMPT, userMessage, "classify");
            IntentResult result = parseResponse(response);

            span.setAttribute("support.intent", result.intent().name());
            span.setAttribute("support.confidence", result.confidence());
            span.setAttribute("support.sub_category", result.subCategory());
            if (!result.entities().isEmpty()) {
                span.setAttribute("support.entities", String.join(",", result.entities()));
            }

            log.debug("Classified intent: {} (confidence={}, sub={})",
                result.intent(), result.confidence(), result.subCategory());
            return result;

        } catch (Exception e) {
            span.setStatus(StatusCode.ERROR, e.getMessage());
            log.error("Intent classification failed, using fallback: {}", e.getMessage());
            return IntentResult.fallback();

        } finally {
            span.end();
        }
    }

    IntentResult parseResponse(LlmResponse response) {
        try {
            String content = response.content().strip();
            if (content.startsWith("```")) {
                content = content.replaceAll("```(?:json)?\\s*", "").replaceAll("```\\s*$", "").strip();
            }

            JsonNode root = mapper.readTree(content);
            Intent intent = Intent.valueOf(root.get("intent").asText().toUpperCase());
            double confidence = root.get("confidence").asDouble();
            String subCategory = root.has("sub_category") ? root.get("sub_category").asText() : "";

            List<String> entities = List.of();
            if (root.has("entities") && root.get("entities").isArray()) {
                entities = new java.util.ArrayList<>();
                for (JsonNode e : root.get("entities")) {
                    entities.add(e.asText());
                }
                entities = List.copyOf(entities);
            }

            return new IntentResult(intent, confidence, subCategory, entities,
                response.inputTokens(), response.outputTokens());

        } catch (Exception e) {
            log.warn("Failed to parse intent response: {}", e.getMessage());
            return new IntentResult(Intent.QUERY, 0.3, "parse_error", List.of(),
                response.inputTokens(), response.outputTokens());
        }
    }
}
