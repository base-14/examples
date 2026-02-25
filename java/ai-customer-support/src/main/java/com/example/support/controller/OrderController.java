package com.example.support.controller;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.example.support.model.Order;
import com.example.support.repository.OrderRepository;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderRepository orderRepo;

    public OrderController(OrderRepository orderRepo) {
        this.orderRepo = orderRepo;
    }

    @GetMapping("/{orderId}")
    public Mono<Order> getByOrderId(@PathVariable String orderId) {
        return orderRepo.findByOrderId(orderId);
    }
}
