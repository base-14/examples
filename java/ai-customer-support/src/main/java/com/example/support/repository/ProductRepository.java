package com.example.support.repository;

import java.util.UUID;

import org.springframework.data.r2dbc.repository.Query;
import org.springframework.data.repository.reactive.ReactiveCrudRepository;

import com.example.support.model.Product;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface ProductRepository extends ReactiveCrudRepository<Product, UUID> {

    Flux<Product> findByCategory(String category);

    Mono<Product> findBySku(String sku);

    @Query("SELECT * FROM products WHERE LOWER(name) LIKE LOWER(CONCAT('%', :query, '%')) " +
           "OR LOWER(description) LIKE LOWER(CONCAT('%', :query, '%'))")
    Flux<Product> searchByName(String query);
}
