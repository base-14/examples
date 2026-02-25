package com.example.support.model;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("messages")
public record Message(
    @Id UUID id,
    UUID conversationId,
    String role,
    String content,
    String intent,
    BigDecimal confidence,
    String[] toolsCalled,
    Integer tokensUsed,
    BigDecimal costUsd,
    String traceId,
    Instant createdAt
) {
    public static Message user(UUID conversationId, String content) {
        return new Message(null, conversationId, "user", content,
            null, null, null, null, null, null, Instant.now());
    }

    public static Message assistant(UUID conversationId, String content,
            String intent, BigDecimal confidence, String[] toolsCalled,
            int tokensUsed, BigDecimal costUsd, String traceId) {
        return new Message(null, conversationId, "assistant", content,
            intent, confidence, toolsCalled, tokensUsed, costUsd, traceId, Instant.now());
    }
}
