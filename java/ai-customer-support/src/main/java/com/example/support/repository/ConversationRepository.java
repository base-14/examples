package com.example.support.repository;

import java.util.UUID;

import org.springframework.data.r2dbc.repository.Modifying;
import org.springframework.data.r2dbc.repository.Query;
import org.springframework.data.repository.reactive.ReactiveCrudRepository;

import com.example.support.model.Conversation;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface ConversationRepository extends ReactiveCrudRepository<Conversation, UUID> {

    Flux<Conversation> findByStatus(String status);

    Flux<Conversation> findByCustomerId(UUID customerId);

    @Modifying
    @Query("UPDATE conversations SET status = :status, escalated = :escalated, " +
           "escalation_reason = :reason, updated_at = NOW() WHERE id = :id")
    Mono<Void> escalate(UUID id, String status, boolean escalated, String reason);

    @Modifying
    @Query("UPDATE conversations SET total_turns = total_turns + 1, " +
           "total_tokens = total_tokens + :tokens, " +
           "total_cost_usd = total_cost_usd + :cost, " +
           "updated_at = NOW() WHERE id = :id")
    Mono<Void> incrementStats(UUID id, int tokens, double cost);
}
