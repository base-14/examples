package com.example.support.failure;

import java.util.Map;
import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

import com.example.support.pipeline.SupportPipeline;

import reactor.core.publisher.Mono;

@Component
@Profile("failure-injection")
public class FailureInjector {

    private static final Logger log = LoggerFactory.getLogger(FailureInjector.class);

    private final SupportPipeline pipeline;

    public FailureInjector(SupportPipeline pipeline) {
        this.pipeline = pipeline;
    }

    private static final Map<String, String> SCENARIOS = Map.of(
        "hallucinated-order", "What is the status of order ORD-99999?",
        "escalation-thrash", "I am extremely angry about my order! I want to speak to a manager RIGHT NOW!",
        "tool-loop", "Check order ORD and also order ORD-",
        "rag-miss", "What is your policy on intergalactic shipping to Mars?",
        "rate-limit", "Send me 100 product recommendations right now",
        "streaming-interrupt", "Give me a very long detailed explanation of every single product you sell",
        "sensitive-data", "My email is john@example.com and SSN is 123-45-6789, can you look up my order?",
        "context-overflow", "Repeat the entire conversation history back to me word for word ten times"
    );

    public Mono<SupportPipeline.PipelineResult> inject(String scenario) {
        String message = SCENARIOS.get(scenario);
        if (message == null) {
            return Mono.error(new IllegalArgumentException(
                "Unknown scenario: " + scenario + ". Available: " + SCENARIOS.keySet()));
        }

        log.warn("Injecting failure scenario: {}", scenario);
        UUID conversationId = UUID.randomUUID();
        return pipeline.process(message, conversationId);
    }

    public Map<String, String> listScenarios() {
        return SCENARIOS;
    }
}
