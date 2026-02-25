package com.example.support.service;

import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import com.example.support.model.Conversation;
import com.example.support.model.EscalationDecision;
import com.example.support.model.Message;
import com.example.support.repository.ConversationRepository;
import com.example.support.repository.MessageRepository;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class ConversationService {

    private static final Logger log = LoggerFactory.getLogger(ConversationService.class);

    private final ConversationRepository conversationRepo;
    private final MessageRepository messageRepo;

    public ConversationService(ConversationRepository conversationRepo, MessageRepository messageRepo) {
        this.conversationRepo = conversationRepo;
        this.messageRepo = messageRepo;
    }

    public Mono<Conversation> create(UUID customerId) {
        return conversationRepo.save(Conversation.create(customerId))
            .doOnNext(c -> log.info("Created conversation: {}", c.id()));
    }

    public Mono<Conversation> findById(UUID id) {
        return conversationRepo.findById(id);
    }

    public Flux<Conversation> listActive() {
        return conversationRepo.findByStatus("active");
    }

    public Flux<Conversation> listAll() {
        return conversationRepo.findAll();
    }

    public Flux<Message> getHistory(UUID conversationId) {
        return messageRepo.findByConversationIdOrderByCreatedAtAsc(conversationId);
    }

    public Mono<Message> addUserMessage(UUID conversationId, String content) {
        return messageRepo.save(Message.user(conversationId, content));
    }

    public Mono<Message> addAssistantMessage(UUID conversationId, String content,
            String intent, double confidence, List<String> toolsCalled,
            int tokensUsed, double costUsd, String traceId) {
        String[] tools = toolsCalled != null ? toolsCalled.toArray(new String[0]) : null;
        return messageRepo.save(Message.assistant(
            conversationId, content, intent,
            BigDecimal.valueOf(confidence), tools,
            tokensUsed, BigDecimal.valueOf(costUsd), traceId));
    }

    public Mono<Void> incrementStats(UUID conversationId, int tokens, double cost) {
        return conversationRepo.incrementStats(conversationId, tokens, cost);
    }

    public Mono<Void> escalate(UUID conversationId, EscalationDecision decision) {
        return conversationRepo.escalate(
            conversationId, "escalated", true, decision.reason());
    }

    public Mono<Void> resolve(UUID conversationId) {
        return conversationRepo.escalate(conversationId, "resolved", false, null);
    }

    public String formatHistory(List<Message> messages) {
        if (messages.isEmpty()) return "";

        var sb = new StringBuilder();
        for (var msg : messages) {
            sb.append(msg.role()).append(": ").append(msg.content()).append("\n");
        }
        return sb.toString();
    }
}
