package com.example.support.controller;

import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;

import com.example.support.pipeline.SupportPipeline;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
public class ChatController {

    private static final Logger log = LoggerFactory.getLogger(ChatController.class);

    private final SupportPipeline pipeline;

    public ChatController(SupportPipeline pipeline) {
        this.pipeline = pipeline;
    }

    public record ChatRequest(String message, UUID conversationId) {}

    public record ChatResponseDto(
        String content,
        String intent,
        double confidence,
        boolean escalated,
        String escalationReason,
        String model,
        String provider,
        int inputTokens,
        int outputTokens,
        double costUsd,
        UUID conversationId
    ) {}

    @PostMapping("/api/chat")
    public Mono<ChatResponseDto> chat(@RequestBody ChatRequest request) {
        if (request.message() == null || request.message().isBlank()) {
            return Mono.error(new ResponseStatusException(HttpStatus.BAD_REQUEST, "Message cannot be empty"));
        }

        UUID conversationId = request.conversationId() != null
            ? request.conversationId() : UUID.randomUUID();

        return pipeline.process(request.message(), conversationId)
            .map(result -> new ChatResponseDto(
                result.content(),
                result.intent().intent().name(),
                result.intent().confidence(),
                result.escalation().shouldEscalate(),
                result.escalation().reason(),
                result.model(),
                result.provider(),
                result.inputTokens(),
                result.outputTokens(),
                result.costUsd(),
                result.conversationId()
            ));
    }

    @PostMapping(value = "/api/chat/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<String> chatStream(@RequestBody ChatRequest request) {
        if (request.message() == null || request.message().isBlank()) {
            return Flux.error(new ResponseStatusException(HttpStatus.BAD_REQUEST, "Message cannot be empty"));
        }

        UUID conversationId = request.conversationId() != null
            ? request.conversationId() : UUID.randomUUID();

        return pipeline.process(request.message(), conversationId)
            .flatMapMany(result -> {
                String[] words = result.content().split("(?<=\\s)");
                return Flux.fromArray(words);
            });
    }
}
