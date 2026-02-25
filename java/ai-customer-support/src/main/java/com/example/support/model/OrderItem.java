package com.example.support.model;

import java.math.BigDecimal;
import java.util.UUID;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("order_items")
public record OrderItem(
    @Id UUID id,
    UUID orderId,
    UUID productId,
    int quantity,
    BigDecimal unitPrice
) {}
