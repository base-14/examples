package com.example.support.repository;

import java.util.UUID;

import org.springframework.data.repository.reactive.ReactiveCrudRepository;

import com.example.support.model.Message;

import reactor.core.publisher.Flux;

public interface MessageRepository extends ReactiveCrudRepository<Message, UUID> {

    Flux<Message> findByConversationIdOrderByCreatedAtAsc(UUID conversationId);
}
