package com.example.support.pipeline;

import java.util.List;
import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import com.example.support.filter.PiiFilter;
import com.example.support.llm.LlmResponse;
import com.example.support.model.EscalationDecision;
import com.example.support.model.IntentResult;
import com.example.support.model.Message;
import com.example.support.service.ConversationService;
import com.example.support.telemetry.SupportMetrics;

import io.opentelemetry.api.GlobalOpenTelemetry;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Component
public class SupportPipeline {

    private static final Logger log = LoggerFactory.getLogger(SupportPipeline.class);

    private final IntentClassifier intentClassifier;
    private final ContextRetriever contextRetriever;
    private final ResponseGenerator responseGenerator;
    private final EscalationRouter escalationRouter;
    private final PiiFilter piiFilter;
    private final SupportMetrics metrics;
    private final ConversationService conversationService;
    private final Tracer tracer;

    public SupportPipeline(
        IntentClassifier intentClassifier,
        ContextRetriever contextRetriever,
        ResponseGenerator responseGenerator,
        EscalationRouter escalationRouter,
        PiiFilter piiFilter,
        SupportMetrics metrics,
        ConversationService conversationService
    ) {
        this.intentClassifier = intentClassifier;
        this.contextRetriever = contextRetriever;
        this.responseGenerator = responseGenerator;
        this.escalationRouter = escalationRouter;
        this.piiFilter = piiFilter;
        this.metrics = metrics;
        this.conversationService = conversationService;
        this.tracer = GlobalOpenTelemetry.getTracer("ai-customer-support");
    }

    public record PipelineResult(
        String content,
        IntentResult intent,
        EscalationDecision escalation,
        String model,
        String provider,
        int inputTokens,
        int outputTokens,
        double costUsd,
        UUID conversationId
    ) {}

    public Mono<PipelineResult> process(String userMessage, UUID conversationId) {
        return conversationService.findById(conversationId)
            .switchIfEmpty(conversationService.create(null).map(c -> c))
            .flatMap(conversation -> {
                UUID convId = conversation.id();

                return conversationService.addUserMessage(convId, userMessage)
                    .then(conversationService.getHistory(convId).collectList())
                    .flatMap(history -> Mono.fromCallable(
                        () -> runPipeline(userMessage, convId, history))
                        .subscribeOn(Schedulers.boundedElastic()))
                    .flatMap(result -> persistResult(convId, userMessage, result)
                        .thenReturn(result));
            });
    }

    private PipelineResult runPipeline(String userMessage, UUID conversationId, List<Message> history) {
        long startNanos = System.nanoTime();
        Span span = tracer.spanBuilder("support_conversation")
            .setAttribute("support.conversation_id", conversationId.toString())
            .startSpan();

        try (Scope ignored = span.makeCurrent()) {
            // 1. Classify intent (fast model)
            IntentResult intent = intentClassifier.classify(userMessage);
            span.setAttribute("support.intent", intent.intent().name());
            span.setAttribute("support.confidence", intent.confidence());

            // 2. Retrieve RAG context
            var ragDocs = contextRetriever.retrieve(userMessage);
            span.setAttribute("support.rag_matches", ragDocs.size());

            // 3. Generate response (capable model)
            String conversationHistory = conversationService.formatHistory(history);
            LlmResponse response = responseGenerator.generate(
                userMessage, intent, ragDocs, conversationHistory);

            // 4. PII scrub
            String content = piiFilter.scrub(response.content());

            // 5. Check escalation
            int turns = history.size() / 2 + 1;
            EscalationDecision escalation = escalationRouter.evaluate(intent, turns, 0);
            span.setAttribute("support.should_escalate", escalation.shouldEscalate());

            // 6. Record domain metrics
            if (!ragDocs.isEmpty()) {
                Double topScore = ragDocs.getFirst().getScore();
                if (topScore != null) {
                    metrics.recordRagSimilarity(topScore, intent.intent().name());
                }
            }
            metrics.recordConversationTurns(turns, intent.intent().name(), false);
            if (escalation.shouldEscalate()) {
                metrics.recordEscalation(escalation.reason(), escalation.priority().name());
            }
            double durationSec = (System.nanoTime() - startNanos) / 1_000_000_000.0;
            metrics.recordConversationDuration(durationSec, intent.intent().name(), escalation.shouldEscalate());

            // Record totals
            int totalTokens = intent.inputTokens() + intent.outputTokens()
                + response.inputTokens() + response.outputTokens();
            span.setAttribute("support.total_turns", (long) turns);
            span.setAttribute("support.total_tokens", (long) totalTokens);
            span.setAttribute("support.total_cost_usd", response.costUsd());

            log.info("Pipeline complete: conv={} intent={} turns={} tokens={} escalate={}",
                conversationId, intent.intent(), turns, totalTokens, escalation.shouldEscalate());

            return new PipelineResult(
                content, intent, escalation,
                response.model(), response.provider(),
                response.inputTokens(), response.outputTokens(),
                response.costUsd(), conversationId);

        } catch (Exception e) {
            span.setStatus(StatusCode.ERROR, e.getMessage());
            log.error("Pipeline failed for conversation {}: {}", conversationId, e.getMessage());
            throw new RuntimeException("Pipeline failed: " + e.getMessage(), e);

        } finally {
            span.end();
        }
    }

    private Mono<Void> persistResult(UUID conversationId, String userMessage, PipelineResult result) {
        int totalTokens = result.inputTokens() + result.outputTokens()
            + result.intent().inputTokens() + result.intent().outputTokens();

        return conversationService.addAssistantMessage(
                conversationId, result.content(),
                result.intent().intent().name(), result.intent().confidence(),
                List.of(), totalTokens, result.costUsd(),
                Span.current().getSpanContext().getTraceId())
            .then(conversationService.incrementStats(conversationId, totalTokens, result.costUsd()))
            .then(result.escalation().shouldEscalate()
                ? conversationService.escalate(conversationId, result.escalation())
                : Mono.empty());
    }
}
