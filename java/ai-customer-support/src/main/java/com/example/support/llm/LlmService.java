package com.example.support.llm;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ThreadLocalRandom;

import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.api.common.Attributes;
import io.opentelemetry.api.metrics.DoubleHistogram;
import io.opentelemetry.api.metrics.LongCounter;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ai.chat.messages.Message;
import org.springframework.ai.chat.messages.SystemMessage;
import org.springframework.ai.chat.messages.UserMessage;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.ai.chat.prompt.ChatOptions;
import org.springframework.ai.chat.prompt.Prompt;
import org.springframework.ai.model.tool.ToolCallingChatOptions;
import org.springframework.ai.model.tool.ToolCallingManager;
import org.springframework.ai.model.tool.ToolExecutionResult;
import org.springframework.ai.tool.ToolCallback;
import org.springframework.stereotype.Service;

import com.example.support.config.AppConfig;
import com.example.support.telemetry.ConversationScope;
import com.example.support.telemetry.GenAi;
import com.example.support.telemetry.Telemetry;

/**
 * Calls the chat model with retry and provider fallback. Spring AI's chat observation
 * produces the {@code chat {model}} span; this class adds the operation duration,
 * retry, fallback and error metrics that sit outside a single model call.
 */
@Service
public class LlmService {

    private static final Logger log = LoggerFactory.getLogger(LlmService.class);
    private static final int MAX_ATTEMPTS = 3;
    private static final int MAX_TOOL_ROUNDS = 8;
    private static final String DEGRADED_ANSWER =
        "I could not finish that request. Please try again, or ask for a human agent.";
    private static final long MIN_BACKOFF_MS = 1000;
    private static final long MAX_BACKOFF_MS = 10000;

    private final ChatModel primaryModel;
    private final ChatModel fallbackModel;
    private final AppConfig config;
    private final Pricing pricing;
    private final ConversationScope conversations;
    private final ToolCallingManager toolCallingManager;
    private final DoubleHistogram operationDuration;
    private final LongCounter retryCounter;
    private final LongCounter fallbackCounter;
    private final LongCounter errorCounter;

    public LlmService(
        Map<String, ChatModel> chatModels,
        AppConfig config,
        Pricing pricing,
        ConversationScope conversations,
        ToolCallingManager toolCallingManager,
        Telemetry telemetry
    ) {
        this.primaryModel = Providers.chatModel(config.provider(), chatModels);
        this.fallbackModel = Providers.chatModel(config.fallbackProvider(), chatModels);
        this.config = config;
        this.pricing = pricing;
        this.conversations = conversations;
        this.toolCallingManager = toolCallingManager;
        log.info("Primary LLM: {} (capable={}, fast={}), Fallback: {} (model={})",
            config.provider(), config.modelCapable(), config.modelFast(),
            config.fallbackProvider(), config.fallbackModel());

        var meter = telemetry.meter();
        this.operationDuration = meter.histogramBuilder(GenAi.OPERATION_DURATION_METRIC)
            .setUnit("s")
            .setDescription("Duration of GenAI operations")
            .build();
        this.retryCounter = meter.counterBuilder(GenAi.RETRY_METRIC)
            .setUnit("{retry}")
            .setDescription("Retry attempts, excluding the initial attempt")
            .build();
        this.fallbackCounter = meter.counterBuilder(GenAi.FALLBACK_METRIC)
            .setUnit("{fallback}")
            .setDescription("Number of fallback triggers")
            .build();
        this.errorCounter = meter.counterBuilder(GenAi.ERROR_METRIC)
            .setUnit("{error}")
            .setDescription("Number of LLM call errors by type")
            .build();
    }

    public LlmResponse generate(String systemPrompt, String userPrompt, String model) {
        return generate(systemPrompt, userPrompt, model, List.of());
    }

    public LlmResponse generate(String systemPrompt, String userPrompt, String model,
                                List<ToolCallback> toolCallbacks) {
        try {
            return generateWithRetry(
                primaryModel, config.provider(), model, systemPrompt, userPrompt, toolCallbacks);
        } catch (RuntimeException primaryFailure) {
            if (fallbackRepeatsPrimary(model)) {
                throw primaryFailure;
            }

            log.warn("Primary provider {} failed, falling back to {}", config.provider(), config.fallbackProvider());
            fallbackCounter.add(1, Attributes.of(
                AttributeKey.stringKey(GenAi.PROVIDER_NAME), config.provider(),
                AttributeKey.stringKey(GenAi.FALLBACK_PROVIDER), config.fallbackProvider()));
            conversations.recordOnConversation(GenAi.FALLBACK_EVENT, Attributes.builder()
                .put(GenAi.FALLBACK_TRIGGERED, true)
                .put(GenAi.PROVIDER_NAME, config.provider())
                .put(GenAi.FALLBACK_PROVIDER, config.fallbackProvider())
                .build());

            try {
                return generateWithRetry(fallbackModel, config.fallbackProvider(), config.fallbackModel(),
                    systemPrompt, userPrompt, toolCallbacks);
            } catch (RuntimeException fallbackFailure) {
                throw new IllegalStateException("All LLM providers failed after retries", fallbackFailure);
            }
        }
    }

    /** A fallback onto the same provider and model would repeat the primary's attempts. */
    private boolean fallbackRepeatsPrimary(String model) {
        return config.fallbackProvider().equals(config.provider())
            && config.fallbackModel().equals(model);
    }

    public LlmResponse generateCapable(String systemPrompt, String userPrompt) {
        return generate(systemPrompt, userPrompt, config.modelCapable());
    }

    public LlmResponse generateCapable(String systemPrompt, String userPrompt, List<ToolCallback> toolCallbacks) {
        return generate(systemPrompt, userPrompt, config.modelCapable(), toolCallbacks);
    }

    public LlmResponse generateFast(String systemPrompt, String userPrompt) {
        return generate(systemPrompt, userPrompt, config.modelFast());
    }

    private LlmResponse generateWithRetry(
        ChatModel chatModel, String provider, String model,
        String systemPrompt, String userPrompt, List<ToolCallback> toolCallbacks
    ) {
        Exception lastError = null;
        for (int attempt = 0; attempt < MAX_ATTEMPTS; attempt++) {
            try {
                return generateOnce(chatModel, provider, model, systemPrompt, userPrompt, toolCallbacks);
            } catch (Exception e) {
                lastError = e;
                log.warn("LLM call failed (attempt {}/{}): provider={} model={} error={}",
                    attempt + 1, MAX_ATTEMPTS, provider, model, e.getMessage());
                if (attempt < MAX_ATTEMPTS - 1) {
                    // The attribute name comes from _shared/test-vectors/chat-with-retry.json.
                    retryCounter.add(1, Attributes.builder()
                        .put(GenAi.PROVIDER_NAME, provider)
                        .put(GenAi.ERROR_TYPE, errorType(e))
                        .put(GenAi.RETRY_ATTEMPT, attempt + 1L)
                        .build());
                    sleep(backoffWithJitter(attempt));
                }
            }
        }

        errorCounter.add(1, Attributes.of(
            AttributeKey.stringKey(GenAi.PROVIDER_NAME), provider,
            AttributeKey.stringKey(GenAi.REQUEST_MODEL), model,
            AttributeKey.stringKey(GenAi.ERROR_TYPE), errorType(lastError)));
        log.error("All {} attempts failed for provider={}", MAX_ATTEMPTS, provider, lastError);
        if (lastError instanceof RuntimeException runtimeError) {
            throw runtimeError;
        }
        throw new IllegalStateException(
            "Provider " + provider + " failed after " + MAX_ATTEMPTS + " attempts", lastError);
    }

    private LlmResponse generateOnce(
        ChatModel chatModel, String provider, String model,
        String systemPrompt, String userPrompt, List<ToolCallback> toolCallbacks
    ) {
        long start = System.nanoTime();
        try {
            Prompt prompt = buildPrompt(chatModel, systemPrompt, userPrompt, model, toolCallbacks);
            ChatResponse response = chatModel.call(prompt);

            // Spring AI 2.0 leaves tool execution to the caller. Running it through the
            // ToolCallingManager keeps the framework's execute_tool observation.
            int toolRounds = 0;
            while (response.hasToolCalls()) {
                if (toolRounds >= MAX_TOOL_ROUNDS) {
                    log.warn("Tool call loop hit the limit of {} rounds, asking for a plain answer",
                        MAX_TOOL_ROUNDS);
                    conversations.recordOnConversation(GenAi.TOOL_LOOP_LIMIT_EVENT, Attributes.of(
                        AttributeKey.longKey(GenAi.TOOL_LOOP_ROUNDS), (long) toolRounds));
                    // Breaking here would leave the caller with a tool-call-only message and no
                    // text, so ask the model once more with the tools taken away.
                    response = chatModel.call(
                        toolFreePrompt(chatModel, prompt.getInstructions(), model));
                    break;
                }
                ToolExecutionResult toolResult = toolCallingManager.executeToolCalls(prompt, response);
                if (toolResult.returnDirect()) {
                    break;
                }
                prompt = new Prompt(toolResult.conversationHistory(), prompt.getOptions());
                response = chatModel.call(prompt);
                toolRounds++;
            }

            var generation = response.getResult();
            var usage = response.getMetadata().getUsage();
            int inputTokens = usage != null && usage.getPromptTokens() != null ? usage.getPromptTokens() : 0;
            int outputTokens = usage != null && usage.getCompletionTokens() != null ? usage.getCompletionTokens() : 0;
            String responseModel = response.getMetadata().getModel() != null && !response.getMetadata().getModel().isBlank()
                ? response.getMetadata().getModel() : model;
            String finishReason = generation != null && generation.getMetadata().getFinishReason() != null
                ? generation.getMetadata().getFinishReason() : "";
            String content = generation != null ? generation.getOutput().getText() : null;
            if (content == null || content.isBlank()) {
                content = DEGRADED_ANSWER;
            }

            operationDuration.record(elapsedSeconds(start), Attributes.of(
                AttributeKey.stringKey(GenAi.OPERATION_NAME), "chat",
                AttributeKey.stringKey(GenAi.PROVIDER_NAME), provider,
                AttributeKey.stringKey(GenAi.REQUEST_MODEL), model));

            return new LlmResponse(
                content, responseModel, provider,
                inputTokens, outputTokens,
                pricing.calculateCost(responseModel, inputTokens, outputTokens), finishReason);

        } catch (Exception e) {
            operationDuration.record(elapsedSeconds(start), Attributes.of(
                AttributeKey.stringKey(GenAi.OPERATION_NAME), "chat",
                AttributeKey.stringKey(GenAi.PROVIDER_NAME), provider,
                AttributeKey.stringKey(GenAi.REQUEST_MODEL), model,
                AttributeKey.stringKey(GenAi.ERROR_TYPE), errorType(e)));
            throw e;
        }
    }

    /**
     * Each provider's ChatModel expects its own ChatOptions type, so the per-call
     * options start from the model's own defaults rather than a generic builder.
     */
    private Prompt buildPrompt(ChatModel chatModel, String systemPrompt, String userPrompt,
                               String model, List<ToolCallback> toolCallbacks) {
        var messages = new ArrayList<Message>();
        if (systemPrompt != null && !systemPrompt.isEmpty()) {
            messages.add(new SystemMessage(systemPrompt));
        }
        messages.add(new UserMessage(userPrompt));

        ChatOptions defaults = chatModel.getDefaultOptions();
        ChatOptions.Builder builder = defaults != null ? defaults.mutate() : ToolCallingChatOptions.builder();
        builder.model(model)
            .temperature(config.temperature())
            .maxTokens(config.maxTokens());

        if (toolCallbacks != null && !toolCallbacks.isEmpty()) {
            if (builder instanceof ToolCallingChatOptions.Builder toolBuilder) {
                toolBuilder.toolCallbacks(toolCallbacks);
            } else {
                log.warn("Dropping {} tool callbacks: {} does not build tool calling options",
                    toolCallbacks.size(), builder.getClass().getName());
            }
        }

        return new Prompt(messages, builder.build());
    }

    /** The same options as a normal call, with every tool removed. */
    private Prompt toolFreePrompt(ChatModel chatModel, List<Message> messages, String model) {
        ChatOptions defaults = chatModel.getDefaultOptions();
        ChatOptions.Builder builder = defaults != null ? defaults.mutate() : ToolCallingChatOptions.builder();
        builder.model(model)
            .temperature(config.temperature())
            .maxTokens(config.maxTokens());

        if (builder instanceof ToolCallingChatOptions.Builder toolBuilder) {
            toolBuilder.toolCallbacks(List.of());
        }

        return new Prompt(messages, builder.build());
    }

    static String errorType(Throwable error) {
        return error != null ? error.getClass().getSimpleName() : "unknown";
    }

    private static double elapsedSeconds(long startNanos) {
        return (System.nanoTime() - startNanos) / 1_000_000_000.0;
    }

    private static long backoffWithJitter(int attempt) {
        long base = Math.min(MIN_BACKOFF_MS * (1L << attempt), MAX_BACKOFF_MS);
        return base + ThreadLocalRandom.current().nextLong(0, base / 4 + 1);
    }

    private static void sleep(long millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
