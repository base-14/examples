package com.example.support.model;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("conversations")
public record Conversation(
    @Id UUID id,
    UUID customerId,
    String status,
    boolean escalated,
    String escalationReason,
    int totalTurns,
    int totalTokens,
    BigDecimal totalCostUsd,
    Instant createdAt,
    Instant updatedAt
) {
    public static Conversation create(UUID customerId) {
        return new Conversation(
            null, customerId, "active", false, null, 0, 0,
            BigDecimal.ZERO, Instant.now(), Instant.now()
        );
    }
}
