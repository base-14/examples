package com.example.support.repository;

import java.util.UUID;

import org.springframework.data.repository.reactive.ReactiveCrudRepository;

import com.example.support.model.Customer;

import reactor.core.publisher.Mono;

public interface CustomerRepository extends ReactiveCrudRepository<Customer, UUID> {

    Mono<Customer> findByEmail(String email);
}
