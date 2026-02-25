package com.example.support.model;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("returns")
public record ReturnRequest(
    @Id UUID id,
    String returnId,
    UUID orderId,
    String reason,
    String status,
    BigDecimal refundAmount,
    Instant createdAt,
    Instant updatedAt
) {}
