package com.example.support.llm;

import java.net.URI;
import java.util.Map;

import org.springframework.ai.chat.model.ChatModel;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/**
 * Server address and port per provider, and the ChatModel bean behind a provider key.
 * The provider key is also the {@code gen_ai.provider.name} value for every provider
 * this example supports.
 */
@Component
public class Providers {

    private static final Map<String, String> SERVERS = Map.of(
        "openai", "api.openai.com",
        "anthropic", "api.anthropic.com"
    );

    private static final Map<String, Long> PORTS = Map.of(
        "openai", 443L,
        "anthropic", 443L
    );

    private final String ollamaHost;
    private final long ollamaPort;

    public Providers(@Value("${spring.ai.ollama.base-url:http://localhost:11434}") String ollamaBaseUrl) {
        URI uri = URI.create(ollamaBaseUrl);
        this.ollamaHost = uri.getHost() != null ? uri.getHost() : "localhost";
        this.ollamaPort = uri.getPort() > 0 ? uri.getPort() : 11434;
    }

    public String serverAddress(String provider) {
        if ("ollama".equals(provider)) {
            return ollamaHost;
        }
        return SERVERS.getOrDefault(provider, "unknown");
    }

    public long serverPort(String provider) {
        if ("ollama".equals(provider)) {
            return ollamaPort;
        }
        return PORTS.getOrDefault(provider, 443L);
    }

    public static ChatModel chatModel(String provider, Map<String, ChatModel> chatModels) {
        String beanName = switch (provider) {
            case "openai" -> "openAiChatModel";
            case "anthropic" -> "anthropicChatModel";
            case "ollama" -> "ollamaChatModel";
            default -> throw new IllegalArgumentException("Unknown LLM provider: " + provider);
        };
        ChatModel model = chatModels.get(beanName);
        if (model == null) {
            throw new IllegalStateException(
                "ChatModel bean '" + beanName + "' not found. Available: " + chatModels.keySet());
        }
        return model;
    }
}
