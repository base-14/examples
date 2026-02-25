package com.example.support.repository;

import java.util.UUID;

import org.springframework.data.repository.reactive.ReactiveCrudRepository;

import com.example.support.model.ReturnRequest;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface ReturnRepository extends ReactiveCrudRepository<ReturnRequest, UUID> {

    Mono<ReturnRequest> findByReturnId(String returnId);

    Flux<ReturnRequest> findByOrderId(UUID orderId);
}
