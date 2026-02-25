package com.example.support.repository;

import java.util.UUID;

import org.springframework.data.repository.reactive.ReactiveCrudRepository;

import com.example.support.model.OrderItem;

import reactor.core.publisher.Flux;

public interface OrderItemRepository extends ReactiveCrudRepository<OrderItem, UUID> {

    Flux<OrderItem> findByOrderId(UUID orderId);
}
