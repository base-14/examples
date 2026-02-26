package com.example.support.llm;

import java.util.List;
import java.util.Map;
import java.util.concurrent.ThreadLocalRandom;

import io.opentelemetry.api.GlobalOpenTelemetry;
import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.api.common.Attributes;
import io.opentelemetry.api.metrics.DoubleCounter;
import io.opentelemetry.api.metrics.DoubleHistogram;
import io.opentelemetry.api.metrics.LongCounter;
import io.opentelemetry.api.metrics.Meter;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ai.chat.messages.SystemMessage;
import org.springframework.ai.chat.messages.UserMessage;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.ai.chat.prompt.ChatOptions;
import org.springframework.ai.chat.prompt.Prompt;
import org.springframework.ai.model.tool.ToolCallingChatOptions;
import org.springframework.ai.tool.ToolCallback;
import org.springframework.stereotype.Service;

import com.example.support.config.AppConfig;
import com.example.support.filter.PiiFilter;

@Service
public class LlmService {

    private static final Logger log = LoggerFactory.getLogger(LlmService.class);
    private static final int MAX_RETRIES = 3;
    private static final long MIN_BACKOFF_MS = 1000;
    private static final long MAX_BACKOFF_MS = 10000;

    private final ChatModel primaryModel;
    private final ChatModel fallbackModel;
    private final AppConfig config;
    private final Pricing pricing;
    private final PiiFilter piiFilter;
    private final boolean captureContent;
    private final Tracer tracer;
    private final DoubleHistogram tokenUsage;
    private final DoubleHistogram operationDuration;
    private final DoubleCounter costCounter;
    private final LongCounter retryCounter;
    private final LongCounter fallbackCounter;
    private final LongCounter errorCounter;

    public LlmService(
        Map<String, ChatModel> chatModels,
        AppConfig config,
        Pricing pricing,
        PiiFilter piiFilter
    ) {
        this.primaryModel = LlmConfig.resolveChatModel(config.provider(), chatModels);
        this.fallbackModel = LlmConfig.resolveChatModel(config.fallbackProvider(), chatModels);
        this.config = config;
        this.pricing = pricing;
        this.piiFilter = piiFilter;
        this.captureContent = "true".equalsIgnoreCase(
            System.getenv("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"));
        log.info("Primary LLM: {} (capable={}, fast={}), Fallback: {} (model={})",
            config.provider(), config.modelCapable(), config.modelFast(),
            config.fallbackProvider(), config.fallbackModel());

        this.tracer = GlobalOpenTelemetry.getTracer("ai-customer-support");
        Meter meter = GlobalOpenTelemetry.getMeter("ai-customer-support");

        this.tokenUsage = meter.histogramBuilder("gen_ai.client.token.usage")
            .setUnit("{token}").build();
        this.operationDuration = meter.histogramBuilder("gen_ai.client.operation.duration")
            .setUnit("s").build();
        this.costCounter = meter.counterBuilder("gen_ai.client.cost")
            .ofDoubles().setUnit("usd").build();
        this.retryCounter = meter.counterBuilder("gen_ai.client.retry.count")
            .build();
        this.fallbackCounter = meter.counterBuilder("gen_ai.client.fallback.count")
            .build();
        this.errorCounter = meter.counterBuilder("gen_ai.client.error.count")
            .build();
    }

    public LlmResponse generate(String systemPrompt, String userPrompt, String model, String stage) {
        return generate(systemPrompt, userPrompt, model, stage, List.of());
    }

    public LlmResponse generate(String systemPrompt, String userPrompt, String model, String stage,
                                 List<ToolCallback> toolCallbacks) {
        var resp = generateWithRetry(primaryModel, config.provider(), model, systemPrompt, userPrompt, stage, toolCallbacks);
        if (resp != null) {
            return resp;
        }

        log.warn("Primary provider {} failed, falling back to {}", config.provider(), config.fallbackProvider());
        fallbackCounter.add(1);

        resp = generateWithRetry(fallbackModel, config.fallbackProvider(), config.fallbackModel(),
            systemPrompt, userPrompt, stage, toolCallbacks);
        if (resp != null) {
            return resp;
        }

        throw new RuntimeException("All LLM providers failed after retries");
    }

    public LlmResponse generateCapable(String systemPrompt, String userPrompt, String stage) {
        return generate(systemPrompt, userPrompt, config.modelCapable(), stage);
    }

    public LlmResponse generateCapable(String systemPrompt, String userPrompt, String stage,
                                         List<ToolCallback> toolCallbacks) {
        return generate(systemPrompt, userPrompt, config.modelCapable(), stage, toolCallbacks);
    }

    public LlmResponse generateFast(String systemPrompt, String userPrompt, String stage) {
        return generate(systemPrompt, userPrompt, config.modelFast(), stage);
    }

    private LlmResponse generateWithRetry(
        ChatModel chatModel, String providerName, String model,
        String systemPrompt, String userPrompt, String stage, List<ToolCallback> toolCallbacks
    ) {
        Exception lastError = null;
        for (int attempt = 0; attempt < MAX_RETRIES; attempt++) {
            try {
                return generateOnce(chatModel, providerName, model, systemPrompt, userPrompt, stage, toolCallbacks);
            } catch (Exception e) {
                lastError = e;
                log.warn("LLM call failed (attempt {}/{}): provider={} model={} error={}",
                    attempt + 1, MAX_RETRIES, providerName, model, e.getMessage());
                if (attempt > 0) {
                    retryCounter.add(1, providerModelAttrs(providerName, model));
                }
                if (attempt < MAX_RETRIES - 1) {
                    sleep(backoffWithJitter(attempt));
                }
            }
        }
        log.error("All {} retries exhausted for provider={}", MAX_RETRIES, providerName, lastError);
        return null;
    }

    private LlmResponse generateOnce(
        ChatModel chatModel, String providerName, String model,
        String systemPrompt, String userPrompt, String stage, List<ToolCallback> toolCallbacks
    ) {
        String spanName = "gen_ai.chat " + model;
        long start = System.nanoTime();

        Span span = tracer.spanBuilder(spanName)
            .setAttribute("gen_ai.operation.name", "chat")
            .setAttribute("gen_ai.provider.name", providerName)
            .setAttribute("gen_ai.request.model", model)
            .setAttribute("server.address", LlmConfig.PROVIDER_SERVERS.getOrDefault(providerName, "unknown"))
            .setAttribute("server.port", (long) LlmConfig.PROVIDER_PORTS.getOrDefault(providerName, 443))
            .setAttribute("gen_ai.request.temperature", config.temperature())
            .setAttribute("gen_ai.request.max_tokens", (long) config.maxTokens())
            .startSpan();

        if (stage != null && !stage.isEmpty()) {
            span.setAttribute("support.stage", stage);
        }

        try (Scope ignored = span.makeCurrent()) {
            if (captureContent) {
                span.addEvent("gen_ai.user.message", Attributes.of(
                    AttributeKey.stringKey("gen_ai.prompt"), truncate(piiFilter.scrub(userPrompt), 1000)
                ));
                if (systemPrompt != null && !systemPrompt.isEmpty()) {
                    span.addEvent("gen_ai.user.message", Attributes.of(
                        AttributeKey.stringKey("gen_ai.system_instructions"), truncate(systemPrompt, 500)
                    ));
                }
            }

            var prompt = buildPrompt(systemPrompt, userPrompt, model, toolCallbacks);
            ChatResponse response = chatModel.call(prompt);

            var generation = response.getResult();
            var metadata = generation.getMetadata();
            var usage = response.getMetadata().getUsage();

            String content = generation.getOutput().getText();
            int inputTokens = usage != null ? (int) usage.getPromptTokens() : 0;
            int outputTokens = usage != null ? (int) usage.getCompletionTokens() : 0;
            String responseModel = response.getMetadata().getModel() != null
                ? response.getMetadata().getModel() : model;
            String finishReason = metadata.getFinishReason() != null
                ? metadata.getFinishReason() : "";
            double costUsd = pricing.calculateCost(responseModel, inputTokens, outputTokens);
            double duration = (System.nanoTime() - start) / 1_000_000_000.0;

            span.setAttribute("gen_ai.response.model", responseModel);
            span.setAttribute("gen_ai.usage.input_tokens", (long) inputTokens);
            span.setAttribute("gen_ai.usage.output_tokens", (long) outputTokens);
            span.setAttribute("gen_ai.usage.cost_usd", costUsd);
            if (!finishReason.isEmpty()) {
                span.setAttribute("gen_ai.response.finish_reasons", finishReason);
            }

            if (captureContent) {
                span.addEvent("gen_ai.assistant.message", Attributes.of(
                    AttributeKey.stringKey("gen_ai.completion"), truncate(piiFilter.scrub(content), 2000)
                ));
            }

            var attrs = providerModelAttrs(providerName, responseModel);
            tokenUsage.record(inputTokens, withTokenType(attrs, "input"));
            tokenUsage.record(outputTokens, withTokenType(attrs, "output"));
            operationDuration.record(duration, attrs);
            costCounter.add(costUsd, attrs);

            return new LlmResponse(content, responseModel, providerName,
                inputTokens, outputTokens, costUsd, finishReason);

        } catch (Exception e) {
            span.setStatus(StatusCode.ERROR, e.getMessage());
            span.setAttribute("error.type", classifyError(e));
            errorCounter.add(1, Attributes.of(
                AttributeKey.stringKey("gen_ai.provider.name"), providerName,
                AttributeKey.stringKey("gen_ai.request.model"), model,
                AttributeKey.stringKey("error.type"), classifyError(e)
            ));
            throw e;
        } finally {
            span.end();
        }
    }

    private Prompt buildPrompt(String systemPrompt, String userPrompt, String model, List<ToolCallback> toolCallbacks) {
        var messages = new java.util.ArrayList<org.springframework.ai.chat.messages.Message>();
        if (systemPrompt != null && !systemPrompt.isEmpty()) {
            messages.add(new SystemMessage(systemPrompt));
        }
        messages.add(new UserMessage(userPrompt));

        if (toolCallbacks != null && !toolCallbacks.isEmpty()) {
            var options = ToolCallingChatOptions.builder()
                .model(model)
                .temperature(config.temperature())
                .maxTokens(config.maxTokens())
                .toolCallbacks(toolCallbacks)
                .build();
            return new Prompt(messages, options);
        }

        var options = ChatOptions.builder()
            .model(model)
            .temperature(config.temperature())
            .maxTokens(config.maxTokens())
            .build();
        return new Prompt(messages, options);
    }

    static String classifyError(Exception e) {
        if (e == null) return "unknown_error";
        String msg = e.getMessage() != null ? e.getMessage().toLowerCase() : "";
        if (msg.contains("rate limit") || msg.contains("429")) return "rate_limit";
        if (msg.contains("timeout") || msg.contains("timed out") || msg.contains("deadline")) return "timeout";
        if (msg.contains("401") || msg.contains("403") || msg.contains("auth") || msg.contains("api key")) return "auth_error";
        if (msg.contains("400") || msg.contains("422") || msg.contains("invalid")) return "invalid_request";
        if (msg.contains("500") || msg.contains("502") || msg.contains("503") || msg.contains("server")) return "server_error";
        if (msg.contains("connect") || msg.contains("dns") || msg.contains("network") || msg.contains("reset")) return "network_error";
        return "unknown_error";
    }

    private long backoffWithJitter(int attempt) {
        long base = Math.min(MIN_BACKOFF_MS * (1L << attempt), MAX_BACKOFF_MS);
        long jitter = ThreadLocalRandom.current().nextLong(0, base / 4 + 1);
        return base + jitter;
    }

    private void sleep(long ms) {
        try {
            Thread.sleep(ms);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    private static String truncate(String s, int max) {
        return s != null && s.length() > max ? s.substring(0, max) : (s != null ? s : "");
    }

    private static Attributes providerModelAttrs(String provider, String model) {
        return Attributes.of(
            AttributeKey.stringKey("gen_ai.operation.name"), "chat",
            AttributeKey.stringKey("gen_ai.provider.name"), provider,
            AttributeKey.stringKey("gen_ai.request.model"), model
        );
    }

    private static Attributes withTokenType(Attributes base, String tokenType) {
        return base.toBuilder()
            .put(AttributeKey.stringKey("gen_ai.token.type"), tokenType)
            .build();
    }
}
