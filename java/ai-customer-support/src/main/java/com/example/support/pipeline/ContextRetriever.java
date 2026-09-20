package com.example.support.pipeline;

import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ai.document.Document;
import org.springframework.ai.vectorstore.SearchRequest;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.stereotype.Component;

import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.api.common.Attributes;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.context.Scope;

import com.example.support.telemetry.ConversationScope;
import com.example.support.telemetry.GenAi;
import com.example.support.telemetry.Telemetry;

/** Knowledge base retrieval over pgvector. */
@Component
public class ContextRetriever {

    private static final Logger log = LoggerFactory.getLogger(ContextRetriever.class);
    private static final int TOP_K = 5;
    private static final String DATA_SOURCE_ID = "kb_articles";

    private final VectorStore vectorStore;
    private final ConversationScope conversations;
    private final Telemetry telemetry;

    public ContextRetriever(VectorStore vectorStore, ConversationScope conversations, Telemetry telemetry) {
        this.vectorStore = vectorStore;
        this.conversations = conversations;
        this.telemetry = telemetry;
    }

    public List<Document> retrieve(String userMessage) {
        var builder = telemetry.tracer().spanBuilder("retrieval " + DATA_SOURCE_ID)
            .setSpanKind(SpanKind.CLIENT)
            .setAttribute(GenAi.OPERATION_NAME, "retrieval")
            .setAttribute(GenAi.DATA_SOURCE_ID, DATA_SOURCE_ID)
            .setAttribute(GenAi.AGENT_NAME, ConversationScope.AGENT_NAME);
        String conversationId = conversations.conversationId();
        if (!conversationId.isEmpty()) {
            builder.setAttribute(GenAi.CONVERSATION_ID, conversationId);
        }
        Span span = builder.startSpan();

        try (Scope ignored = span.makeCurrent()) {
            List<Document> results = vectorStore.similaritySearch(
                SearchRequest.builder()
                    .query(userMessage)
                    .topK(TOP_K)
                    .build()
            );

            span.setAttribute("app.retrieval.matches", results.size());
            if (!results.isEmpty()) {
                Double topScore = results.getFirst().getScore();
                if (topScore != null) {
                    span.setAttribute("app.retrieval.top_similarity", topScore);
                }
            }
            return results;

        } catch (Exception e) {
            span.recordException(e);
            span.setAttribute(GenAi.ERROR_TYPE, e.getClass().getSimpleName());
            span.setStatus(StatusCode.ERROR, e.getMessage());
            conversations.recordOnConversation(GenAi.RETRIEVAL_DEGRADED_EVENT, Attributes.of(
                AttributeKey.stringKey(GenAi.DATA_SOURCE_ID), DATA_SOURCE_ID,
                AttributeKey.stringKey(GenAi.ERROR_TYPE), e.getClass().getSimpleName()));
            log.error("Knowledge base retrieval failed, continuing without context: {}", e.getMessage());
            return List.of();

        } finally {
            span.end();
        }
    }

    public String formatContext(List<Document> documents) {
        if (documents.isEmpty()) {
            return "";
        }

        var sb = new StringBuilder("Relevant knowledge base articles:\n\n");
        for (int i = 0; i < documents.size(); i++) {
            sb.append("--- Article ").append(i + 1).append(" ---\n");
            sb.append(documents.get(i).getText()).append("\n\n");
        }
        return sb.toString();
    }
}
