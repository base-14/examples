package com.example.support.service;

import java.util.List;
import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ai.document.Document;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

@Service
public class KnowledgeBaseService implements ApplicationRunner {

    private static final Logger log = LoggerFactory.getLogger(KnowledgeBaseService.class);

    private final VectorStore vectorStore;
    private final JdbcTemplate jdbcTemplate;

    public KnowledgeBaseService(VectorStore vectorStore, JdbcTemplate jdbcTemplate) {
        this.vectorStore = vectorStore;
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public void run(ApplicationArguments args) {
        int existing = jdbcTemplate.queryForObject(
            "SELECT COUNT(*) FROM vector_store", Integer.class);
        if (existing > 0) {
            log.info("Vector store already populated with {} documents, skipping KB load", existing);
            return;
        }

        log.info("Loading KB articles into vector store...");
        List<Map<String, Object>> articles = jdbcTemplate.queryForList(
            "SELECT id, intent, question, answer, category FROM kb_articles");

        List<Document> docs = articles.stream()
            .map(row -> {
                String content = row.get("question") + "\n\n" + row.get("answer");
                Map<String, Object> metadata = Map.of(
                    "intent", row.get("intent"),
                    "category", row.get("category") != null ? row.get("category") : "",
                    "source", "kb_article",
                    "article_id", row.get("id").toString()
                );
                return new Document(content, metadata);
            })
            .toList();

        vectorStore.add(docs);
        log.info("Loaded {} KB articles into vector store", docs.size());
    }
}
