package com.example.support.controller;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.example.support.model.Product;
import com.example.support.repository.ProductRepository;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/products")
public class ProductController {

    private final ProductRepository productRepo;

    public ProductController(ProductRepository productRepo) {
        this.productRepo = productRepo;
    }

    @GetMapping
    public Flux<Product> list() {
        return productRepo.findAll();
    }

    @GetMapping("/{sku}")
    public Mono<Product> getBySku(@PathVariable String sku) {
        return productRepo.findBySku(sku);
    }
}
