package com.example.support.llm;

import java.util.Map;

import org.springframework.ai.chat.model.ChatModel;
import org.springframework.context.annotation.Configuration;

@Configuration
public class LlmConfig {

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

    public static ChatModel resolveChatModel(String provider, Map<String, ChatModel> chatModels) {
        String beanName = switch (provider) {
            case "openai" -> "openAiChatModel";
            case "anthropic" -> "anthropicChatModel";
            case "ollama" -> "ollamaChatModel";
            default -> throw new IllegalArgumentException("Unknown LLM provider: " + provider);
        };
        var model = chatModels.get(beanName);
        if (model == null) {
            throw new IllegalStateException(
                "ChatModel bean '" + beanName + "' not found. Available: " + chatModels.keySet());
        }
        return model;
    }
}
