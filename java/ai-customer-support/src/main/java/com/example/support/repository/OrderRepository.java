package com.example.support.repository;

import java.util.UUID;

import org.springframework.data.repository.reactive.ReactiveCrudRepository;

import com.example.support.model.Order;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface OrderRepository extends ReactiveCrudRepository<Order, UUID> {

    Mono<Order> findByOrderId(String orderId);

    Flux<Order> findByCustomerIdOrderByCreatedAtDesc(UUID customerId);
}
