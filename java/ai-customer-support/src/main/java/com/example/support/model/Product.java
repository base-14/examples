package com.example.support.model;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("products")
public record Product(
    @Id UUID id,
    String name,
    String description,
    String category,
    BigDecimal price,
    String sku,
    boolean inStock,
    Instant createdAt
) {}
