package com.example.support.controller;

import java.util.UUID;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.example.support.model.Conversation;
import com.example.support.model.EscalationDecision;
import com.example.support.model.Message;
import com.example.support.service.ConversationService;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/conversations")
public class ConversationController {

    private final ConversationService conversationService;

    public ConversationController(ConversationService conversationService) {
        this.conversationService = conversationService;
    }

    public record ConversationDetail(Conversation conversation, java.util.List<Message> messages) {}

    @GetMapping
    public Flux<Conversation> list() {
        return conversationService.listAll();
    }

    @GetMapping("/{id}")
    public Mono<ConversationDetail> get(@PathVariable UUID id) {
        return conversationService.findById(id)
            .zipWith(conversationService.getHistory(id).collectList())
            .map(tuple -> new ConversationDetail(tuple.getT1(), tuple.getT2()));
    }

    @PostMapping("/{id}/escalate")
    public Mono<Void> escalate(@PathVariable UUID id) {
        return conversationService.escalate(id,
            EscalationDecision.escalate("manual_request",
                EscalationDecision.EscalationPriority.HIGH, "Manually escalated via API"));
    }

    @PostMapping("/{id}/resolve")
    public Mono<Void> resolve(@PathVariable UUID id) {
        return conversationService.resolve(id);
    }
}
