package com.example.support.model;

import java.time.Instant;
import java.util.UUID;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public record Customer(
    @Id UUID id,
    String name,
    String email,
    Instant createdAt
) {}
