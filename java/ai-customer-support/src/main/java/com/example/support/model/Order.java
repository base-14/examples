package com.example.support.model;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("orders")
public record Order(
    @Id UUID id,
    String orderId,
    UUID customerId,
    String status,
    String trackingNumber,
    LocalDate estimatedDelivery,
    BigDecimal totalAmount,
    Instant createdAt,
    Instant updatedAt
) {}
