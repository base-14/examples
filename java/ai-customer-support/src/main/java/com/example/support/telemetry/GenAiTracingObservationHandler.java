package com.example.support.telemetry;

import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.stream.Collectors;

import io.micrometer.observation.Observation;
import io.micrometer.tracing.Tracer;
import io.micrometer.tracing.handler.DefaultTracingObservationHandler;
import io.micrometer.tracing.otel.bridge.OtelSpan;
import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.api.common.Attributes;
import io.opentelemetry.api.common.AttributesBuilder;
import io.opentelemetry.api.metrics.DoubleCounter;
import io.opentelemetry.api.trace.Span;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ai.chat.messages.Message;
import org.springframework.ai.chat.messages.MessageType;
import org.springframework.ai.chat.metadata.Usage;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.ai.chat.observation.ChatModelObservationContext;
import org.springframework.ai.embedding.EmbeddingResponse;
import org.springframework.ai.embedding.observation.EmbeddingModelObservationContext;
import org.springframework.ai.tool.observation.ToolCallingObservationContext;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

import com.example.support.filter.PiiFilter;
import com.example.support.llm.Pricing;
import com.example.support.llm.Providers;

/**
 * Maps Spring AI's chat, embedding and tool observations onto GenAI semconv spans:
 * CLIENT kind for model calls, typed token, finish reason and cost attributes, and the
 * gated inference content event. Spring AI stays the only source of these spans.
 */
@Component
// Boot groups tracing handlers into a first-matching composite. Running first means this
// handler claims every GenAI context, so the default tracing handler never opens a second
// span for one; contexts this handler does not support still fall through to it.
@Order(Ordered.HIGHEST_PRECEDENCE)
public class GenAiTracingObservationHandler extends DefaultTracingObservationHandler {

    private static final Logger log = LoggerFactory.getLogger(GenAiTracingObservationHandler.class);
    private static final AtomicBoolean unwrapWarned = new AtomicBoolean();

    private static final int INPUT_MAX_CHARS = 1000;
    private static final int SYSTEM_MAX_CHARS = 500;
    private static final int OUTPUT_MAX_CHARS = 2000;

    private final Pricing pricing;
    private final Providers providers;
    private final ConversationScope conversations;
    private final PiiFilter piiFilter;
    private final boolean captureContent;
    private final DoubleCounter costCounter;

    public GenAiTracingObservationHandler(
        Tracer tracer,
        Telemetry telemetry,
        Pricing pricing,
        Providers providers,
        ConversationScope conversations,
        PiiFilter piiFilter,
        @Value("${OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT:false}") boolean captureContent
    ) {
        super(tracer);
        this.pricing = pricing;
        this.providers = providers;
        this.conversations = conversations;
        this.piiFilter = piiFilter;
        this.captureContent = captureContent;
        this.costCounter = telemetry.meter()
            .counterBuilder(GenAi.COST_METRIC)
            .ofDoubles()
            .setUnit("usd")
            .setDescription("Cost of GenAI operations in USD")
            .build();
    }

    @Override
    public boolean supportsContext(Observation.Context context) {
        return context instanceof ChatModelObservationContext
            || context instanceof EmbeddingModelObservationContext
            || context instanceof ToolCallingObservationContext;
    }

    /**
     * An embedding request often carries no model of its own, so the name would end up as
     * a bare {@code embeddings}. The response knows the model, and the default handler
     * applies this name again when the observation stops.
     */
    @Override
    public String getSpanName(Observation.Context context) {
        if (context instanceof EmbeddingModelObservationContext embedding) {
            EmbeddingResponse response = embedding.getResponse();
            String model = response != null ? response.getMetadata().getModel() : null;
            if (model != null && !model.isBlank()) {
                return "embeddings " + model;
            }
        }
        return super.getSpanName(context);
    }

    @Override
    public void onStart(Observation.Context context) {
        io.micrometer.tracing.Span parent = getParentSpan(context);
        io.micrometer.tracing.Span.Builder builder = getTracer().spanBuilder().name(getSpanName(context));
        if (!(context instanceof ToolCallingObservationContext)) {
            builder = builder.kind(io.micrometer.tracing.Span.Kind.CLIENT);
        }
        if (parent != null) {
            builder = builder.setParent(parent.context());
        }
        io.micrometer.tracing.Span span = builder.start();
        getTracingContext(context).setSpan(span);
        applyStartAttributes(context, otel(span));
    }

    @Override
    public void onStop(Observation.Context context) {
        if (context instanceof ChatModelObservationContext chat) {
            applyResponseAttributes(chat, otel(getRequiredSpan(context)));
        }
        super.onStop(context);
    }

    @Override
    public void onError(Observation.Context context) {
        Span span = otel(getRequiredSpan(context));
        Throwable error = context.getError();
        if (error != null) {
            span.setAttribute(GenAi.ERROR_TYPE, error.getClass().getSimpleName());
        }
        if (captureContent && context instanceof ChatModelObservationContext chat) {
            span.addEvent(GenAi.INFERENCE_DETAILS_EVENT, contentAttributes(chat, null));
        }
        super.onError(context);
    }

    private void applyStartAttributes(Observation.Context context, Span span) {
        span.setAttribute(GenAi.AGENT_NAME, ConversationScope.AGENT_NAME);
        String conversationId = conversations.conversationId();
        if (!conversationId.isEmpty()) {
            span.setAttribute(GenAi.CONVERSATION_ID, conversationId);
        }

        if (context instanceof ChatModelObservationContext chat) {
            applyServer(span, chat.getOperationMetadata().provider());
        } else if (context instanceof EmbeddingModelObservationContext embedding) {
            applyServer(span, embedding.getOperationMetadata().provider());
        } else if (context instanceof ToolCallingObservationContext tool) {
            span.setAttribute(GenAi.TOOL_NAME, tool.getToolDefinition().name());
            String toolCallId = tool.getToolCallId();
            if (toolCallId != null && !toolCallId.isBlank()) {
                span.setAttribute(GenAi.TOOL_CALL_ID, toolCallId);
            }
        }
    }

    private void applyServer(Span span, String provider) {
        span.setAttribute(GenAi.SERVER_ADDRESS, providers.serverAddress(provider));
        span.setAttribute(GenAi.SERVER_PORT, providers.serverPort(provider));
    }

    private void applyResponseAttributes(ChatModelObservationContext context, Span span) {
        ChatResponse response = context.getResponse();
        if (response == null) {
            return;
        }

        Usage usage = response.getMetadata().getUsage();
        long inputTokens = usage != null && usage.getPromptTokens() != null ? usage.getPromptTokens() : 0;
        long outputTokens = usage != null && usage.getCompletionTokens() != null ? usage.getCompletionTokens() : 0;
        span.setAttribute(GenAi.USAGE_INPUT_TOKENS, inputTokens);
        span.setAttribute(GenAi.USAGE_OUTPUT_TOKENS, outputTokens);

        List<String> finishReasons = response.getResults().stream()
            .map(generation -> generation.getMetadata().getFinishReason())
            .filter(reason -> reason != null && !reason.isBlank())
            .toList();
        if (!finishReasons.isEmpty()) {
            span.setAttribute(AttributeKey.stringArrayKey(GenAi.RESPONSE_FINISH_REASONS), finishReasons);
        }

        String model = responseModel(context, response);
        double cost = pricing.calculateCost(model, (int) inputTokens, (int) outputTokens);
        span.setAttribute(GenAi.COST_USD, cost);
        costCounter.add(cost, Attributes.of(
            AttributeKey.stringKey(GenAi.OPERATION_NAME), context.getOperationMetadata().operationType(),
            AttributeKey.stringKey(GenAi.PROVIDER_NAME), context.getOperationMetadata().provider(),
            AttributeKey.stringKey(GenAi.REQUEST_MODEL), requestModel(context, model)));

        if (captureContent) {
            span.addEvent(GenAi.INFERENCE_DETAILS_EVENT, contentAttributes(context, response));
        }
    }

    private static String requestModel(ChatModelObservationContext context, String fallback) {
        var options = context.getRequest().getOptions();
        return options != null && options.getModel() != null && !options.getModel().isBlank()
            ? options.getModel() : fallback;
    }

    private static String responseModel(ChatModelObservationContext context, ChatResponse response) {
        String model = response.getMetadata().getModel();
        if (model != null && !model.isBlank()) {
            return model;
        }
        var options = context.getRequest().getOptions();
        return options != null && options.getModel() != null ? options.getModel() : "unknown";
    }

    /** A null response is the failure path, where the call produced no output messages. */
    private Attributes contentAttributes(ChatModelObservationContext context, ChatResponse response) {
        List<Message> messages = context.getRequest().getInstructions();
        String system = joinText(messages, true);
        String input = joinText(messages, false);

        AttributesBuilder attributes = Attributes.builder()
            .put(GenAi.INPUT_MESSAGES, truncate(piiFilter.scrub(input), INPUT_MAX_CHARS));
        if (response != null) {
            String output = response.getResults().stream()
                .map(generation -> generation.getOutput().getText())
                .filter(text -> text != null && !text.isBlank())
                .collect(Collectors.joining("\n"));
            attributes.put(GenAi.OUTPUT_MESSAGES, truncate(piiFilter.scrub(output), OUTPUT_MAX_CHARS));
        }
        if (!system.isBlank()) {
            attributes.put(GenAi.SYSTEM_INSTRUCTIONS, truncate(piiFilter.scrub(system), SYSTEM_MAX_CHARS));
        }
        return attributes.build();
    }

    private static String joinText(List<Message> messages, boolean systemMessages) {
        return messages.stream()
            .filter(message -> (message.getMessageType() == MessageType.SYSTEM) == systemMessages)
            .map(Message::getText)
            .filter(text -> text != null && !text.isBlank())
            .collect(Collectors.joining("\n"));
    }

    private static String truncate(String text, int max) {
        if (text == null) {
            return "";
        }
        return text.length() > max ? text.substring(0, max) : text;
    }

    private static Span otel(io.micrometer.tracing.Span span) {
        if (span instanceof OtelSpan) {
            return OtelSpan.toOtel(span);
        }
        if (unwrapWarned.compareAndSet(false, true)) {
            log.warn("Micrometer span is a {}, not an OtelSpan: the typed GenAI attributes are being dropped",
                span != null ? span.getClass().getName() : "null");
        }
        return Span.getInvalid();
    }
}
