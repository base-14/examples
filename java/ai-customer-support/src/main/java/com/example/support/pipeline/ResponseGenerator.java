package com.example.support.pipeline;

import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ai.document.Document;
import org.springframework.stereotype.Component;

import com.example.support.llm.LlmResponse;
import com.example.support.llm.LlmService;
import com.example.support.model.IntentResult;

import io.opentelemetry.api.GlobalOpenTelemetry;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;

@Component
public class ResponseGenerator {

    private static final Logger log = LoggerFactory.getLogger(ResponseGenerator.class);

    private static final String SYSTEM_PROMPT_TEMPLATE = """
        You are a helpful customer support agent for TechMart, an online electronics retailer.

        Guidelines:
        - Be concise and helpful (under 200 words)
        - Confirm actions before performing them
        - Acknowledge complaints with empathy
        - Reference specific order/product details when available
        - If you don't know something, say so honestly
        - Never make up order statuses or tracking information

        Customer intent: %s (confidence: %.0f%%)

        %s
        %s""";

    private final LlmService llmService;
    private final ContextRetriever contextRetriever;
    private final Tracer tracer;

    public ResponseGenerator(LlmService llmService, ContextRetriever contextRetriever) {
        this.llmService = llmService;
        this.contextRetriever = contextRetriever;
        this.tracer = GlobalOpenTelemetry.getTracer("ai-customer-support");
    }

    public LlmResponse generate(String userMessage, IntentResult intent,
                                 List<Document> ragContext, String conversationHistory) {
        Span span = tracer.spanBuilder("generate_response")
            .setAttribute("support.stage", "generate")
            .setAttribute("support.rag_matches_used", ragContext.size())
            .startSpan();

        try (Scope ignored = span.makeCurrent()) {
            String ragSection = contextRetriever.formatContext(ragContext);
            String historySection = conversationHistory != null && !conversationHistory.isEmpty()
                ? "Previous conversation:\n" + conversationHistory + "\n"
                : "";

            String systemPrompt = SYSTEM_PROMPT_TEMPLATE.formatted(
                intent.intent().name(),
                intent.confidence() * 100,
                ragSection,
                historySection
            );

            LlmResponse response = llmService.generateCapable(systemPrompt, userMessage, "generate");

            span.setAttribute("gen_ai.usage.input_tokens", (long) response.inputTokens());
            span.setAttribute("gen_ai.usage.output_tokens", (long) response.outputTokens());
            span.setAttribute("gen_ai.usage.cost_usd", response.costUsd());

            log.debug("Generated response: {} tokens (in={}, out={})",
                response.inputTokens() + response.outputTokens(),
                response.inputTokens(), response.outputTokens());
            return response;

        } catch (Exception e) {
            span.setStatus(StatusCode.ERROR, e.getMessage());
            log.error("Response generation failed: {}", e.getMessage());
            throw e;

        } finally {
            span.end();
        }
    }
}
