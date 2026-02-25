package com.example.support.llm;

import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import com.example.support.config.AppConfig;

@Configuration
public class LlmConfig {

    private static final Logger log = LoggerFactory.getLogger(LlmConfig.class);

    public static final Map<String, String> PROVIDER_SERVERS = Map.of(
        "openai", "api.openai.com",
        "anthropic", "api.anthropic.com",
        "google", "generativelanguage.googleapis.com",
        "ollama", "localhost"
    );

    public static final Map<String, Integer> PROVIDER_PORTS = Map.of(
        "openai", 443,
        "anthropic", 443,
        "google", 443,
        "ollama", 11434
    );

    @Bean
    @Qualifier("primaryChatModel")
    ChatModel primaryChatModel(
        AppConfig config,
        Map<String, ChatModel> chatModels
    ) {
        var model = resolveChatModel(config.provider(), chatModels);
        log.info("Primary LLM provider: {} (capable={}, fast={})",
            config.provider(), config.modelCapable(), config.modelFast());
        return model;
    }

    @Bean
    @Qualifier("fallbackChatModel")
    ChatModel fallbackChatModel(
        AppConfig config,
        Map<String, ChatModel> chatModels
    ) {
        var model = resolveChatModel(config.fallbackProvider(), chatModels);
        log.info("Fallback LLM provider: {} (model={})",
            config.fallbackProvider(), config.fallbackModel());
        return model;
    }

    private ChatModel resolveChatModel(String provider, Map<String, ChatModel> chatModels) {
        // Spring AI auto-registers beans with names like "openAiChatModel", "anthropicChatModel", etc.
        return switch (provider) {
            case "openai" -> findBean(chatModels, "openAiChatModel");
            case "anthropic" -> findBean(chatModels, "anthropicChatModel");
            case "ollama" -> findBean(chatModels, "ollamaChatModel");
            default -> throw new IllegalArgumentException("Unknown LLM provider: " + provider);
        };
    }

    private ChatModel findBean(Map<String, ChatModel> chatModels, String name) {
        var model = chatModels.get(name);
        if (model == null) {
            throw new IllegalStateException(
                "ChatModel bean '" + name + "' not found. Available: " + chatModels.keySet());
        }
        return model;
    }
}
