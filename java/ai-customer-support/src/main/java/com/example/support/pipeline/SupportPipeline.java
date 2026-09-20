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
import com.example.support.telemetry.ConversationScope;
import com.example.support.telemetry.GenAi;
import com.example.support.telemetry.SupportMetrics;
import com.example.support.telemetry.Telemetry;

import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.context.Scope;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

/** Classify, retrieve, generate, scrub, route. One conversation span per turn. */
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
    private final ConversationScope conversations;
    private final Telemetry telemetry;

    public SupportPipeline(
        IntentClassifier intentClassifier,
        ContextRetriever contextRetriever,
        ResponseGenerator responseGenerator,
        EscalationRouter escalationRouter,
        PiiFilter piiFilter,
        SupportMetrics metrics,
        ConversationService conversationService,
        ConversationScope conversations,
        Telemetry telemetry
    ) {
        this.intentClassifier = intentClassifier;
        this.contextRetriever = contextRetriever;
        this.responseGenerator = responseGenerator;
        this.escalationRouter = escalationRouter;
        this.piiFilter = piiFilter;
        this.metrics = metrics;
        this.conversationService = conversationService;
        this.conversations = conversations;
        this.telemetry = telemetry;
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
                    .flatMap(result -> persistResult(convId, result)
                        .thenReturn(result));
            });
    }

    private PipelineResult runPipeline(String userMessage, UUID conversationId, List<Message> history) {
        long startNanos = System.nanoTime();
        Span span = telemetry.tracer().spanBuilder("support_conversation")
            .setAttribute(GenAi.CONVERSATION_ID, conversationId.toString())
            .setAttribute(GenAi.AGENT_NAME, ConversationScope.AGENT_NAME)
            .startSpan();
        conversations.begin(conversationId.toString(), span);

        try (Scope ignored = span.makeCurrent()) {
            IntentResult intent = intentClassifier.classify(userMessage);
            span.setAttribute("base14.support.intent", intent.intent().name());
            span.setAttribute("base14.support.confidence", intent.confidence());

            var ragDocs = contextRetriever.retrieve(userMessage);
            span.setAttribute("base14.support.rag_matches", ragDocs.size());

            String conversationHistory = conversationService.formatHistory(history);
            LlmResponse response = responseGenerator.generate(
                userMessage, intent, ragDocs, conversationHistory);

            String content = piiFilter.evaluate(response.content());

            int turns = history.size() / 2 + 1;
            EscalationDecision escalation = escalationRouter.evaluate(intent, turns, 0);
            span.setAttribute("base14.support.should_escalate", escalation.shouldEscalate());

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

            int totalTokens = intent.inputTokens() + intent.outputTokens()
                + response.inputTokens() + response.outputTokens();
            span.setAttribute("base14.support.total_turns", (long) turns);
            span.setAttribute("base14.support.total_tokens", (long) totalTokens);
            span.setAttribute("base14.support.total_cost_usd", response.costUsd());

            log.info("Pipeline complete: conv={} intent={} turns={} tokens={} escalate={}",
                conversationId, intent.intent(), turns, totalTokens, escalation.shouldEscalate());

            return new PipelineResult(
                content, intent, escalation,
                response.model(), response.provider(),
                response.inputTokens(), response.outputTokens(),
                response.costUsd(), conversationId);

        } catch (Exception e) {
            span.recordException(e);
            span.setAttribute(GenAi.ERROR_TYPE, e.getClass().getSimpleName());
            span.setStatus(StatusCode.ERROR, e.getMessage());
            log.error("Pipeline failed for conversation {}: {}", conversationId, e.getMessage());
            throw new IllegalStateException("Pipeline failed: " + e.getMessage(), e);

        } finally {
            conversations.end();
            span.end();
        }
    }

    private Mono<Void> persistResult(UUID conversationId, PipelineResult result) {
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
