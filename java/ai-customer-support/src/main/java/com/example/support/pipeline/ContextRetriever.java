package com.example.support.pipeline;

import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ai.document.Document;
import org.springframework.ai.vectorstore.SearchRequest;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.stereotype.Component;

import io.opentelemetry.api.GlobalOpenTelemetry;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;

@Component
public class ContextRetriever {

    private static final Logger log = LoggerFactory.getLogger(ContextRetriever.class);
    private static final int TOP_K = 5;

    private final VectorStore vectorStore;
    private final Tracer tracer;

    public ContextRetriever(VectorStore vectorStore) {
        this.vectorStore = vectorStore;
        this.tracer = GlobalOpenTelemetry.getTracer("ai-customer-support");
    }

    public List<Document> retrieve(String userMessage) {
        Span span = tracer.spanBuilder("rag_retrieval")
            .setAttribute("support.stage", "retrieve")
            .startSpan();

        try (Scope ignored = span.makeCurrent()) {
            List<Document> results = vectorStore.similaritySearch(
                SearchRequest.builder()
                    .query(userMessage)
                    .topK(TOP_K)
                    .build()
            );

            span.setAttribute("support.matches_found", results.size());
            if (!results.isEmpty()) {
                Double topScore = results.getFirst().getScore();
                if (topScore != null) {
                    span.setAttribute("support.top_similarity", topScore);
                }
            }

            log.debug("RAG retrieved {} matches for query: {}", results.size(),
                userMessage.length() > 80 ? userMessage.substring(0, 80) + "..." : userMessage);
            return results;

        } catch (Exception e) {
            span.setStatus(io.opentelemetry.api.trace.StatusCode.ERROR, e.getMessage());
            log.error("RAG retrieval failed: {}", e.getMessage());
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
            var doc = documents.get(i);
            sb.append("--- Article ").append(i + 1).append(" ---\n");
            sb.append(doc.getText()).append("\n\n");
        }
        return sb.toString();
    }
}
