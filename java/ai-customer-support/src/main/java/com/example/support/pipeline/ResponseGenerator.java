package com.example.support.pipeline;

import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ai.document.Document;
import org.springframework.ai.tool.ToolCallback;
import org.springframework.ai.tool.method.MethodToolCallbackProvider;
import org.springframework.stereotype.Component;

import com.example.support.llm.LlmResponse;
import com.example.support.llm.LlmService;
import com.example.support.model.IntentResult;
import com.example.support.telemetry.GenAi;
import com.example.support.telemetry.Telemetry;
import com.example.support.tools.OrderTools;
import com.example.support.tools.ProductTools;

import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.context.Scope;

/** Builds the agent prompt and asks the capable model for the customer-facing reply. */
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
        - Use the available tools to look up real order and product information
        - Never make up order statuses or tracking information

        Customer intent: %s (confidence: %.0f%%)

        %s
        %s""";

    private final LlmService llmService;
    private final ContextRetriever contextRetriever;
    private final List<ToolCallback> toolCallbacks;
    private final Telemetry telemetry;

    public ResponseGenerator(LlmService llmService, ContextRetriever contextRetriever,
                             Telemetry telemetry,
                             OrderTools orderTools, ProductTools productTools) {
        this.llmService = llmService;
        this.contextRetriever = contextRetriever;
        this.telemetry = telemetry;
        this.toolCallbacks = List.of(
            MethodToolCallbackProvider.builder()
                .toolObjects(orderTools, productTools)
                .build()
                .getToolCallbacks()
        );
    }

    public LlmResponse generate(String userMessage, IntentResult intent,
                                List<Document> ragContext, String conversationHistory) {
        Span span = telemetry.tracer().spanBuilder("generate_response")
            .setAttribute("base14.support.stage", "generate")
            .setAttribute("base14.support.rag_matches_used", ragContext.size())
            .startSpan();

        try (Scope ignored = span.makeCurrent()) {
            String historySection = conversationHistory != null && !conversationHistory.isEmpty()
                ? "Previous conversation:\n" + conversationHistory + "\n"
                : "";

            String systemPrompt = SYSTEM_PROMPT_TEMPLATE.formatted(
                intent.intent().name(),
                intent.confidence() * 100,
                contextRetriever.formatContext(ragContext),
                historySection
            );

            LlmResponse response = llmService.generateCapable(systemPrompt, userMessage, toolCallbacks);
            log.debug("Generated response: {} tokens (in={}, out={})",
                response.inputTokens() + response.outputTokens(),
                response.inputTokens(), response.outputTokens());
            return response;

        } catch (Exception e) {
            span.recordException(e);
            span.setAttribute(GenAi.ERROR_TYPE, e.getClass().getSimpleName());
            span.setStatus(StatusCode.ERROR, e.getMessage());
            log.error("Response generation failed: {}", e.getMessage());
            throw e;

        } finally {
            span.end();
        }
    }
}
