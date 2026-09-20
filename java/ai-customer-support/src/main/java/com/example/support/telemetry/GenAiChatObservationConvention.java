package com.example.support.telemetry;

import java.util.List;
import java.util.Set;

import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;

import org.springframework.ai.chat.observation.ChatModelObservationContext;
import org.springframework.ai.chat.observation.DefaultChatModelObservationConvention;
import org.springframework.stereotype.Component;

/**
 * Spring AI's chat convention with {@code gen_ai.system} replaced by
 * {@code gen_ai.provider.name}. Token counts and finish reasons are left out here
 * because {@link GenAiTracingObservationHandler} sets them as typed span attributes.
 */
@Component
public class GenAiChatObservationConvention extends DefaultChatModelObservationConvention {

    private static final Set<String> TYPED_ON_SPAN = Set.of(
        GenAi.USAGE_INPUT_TOKENS, GenAi.USAGE_OUTPUT_TOKENS, GenAi.RESPONSE_FINISH_REASONS);

    @Override
    public KeyValues getLowCardinalityKeyValues(ChatModelObservationContext context) {
        return KeyValues.of(
            KeyValue.of(GenAi.OPERATION_NAME, context.getOperationMetadata().operationType()),
            KeyValue.of(GenAi.PROVIDER_NAME, context.getOperationMetadata().provider()),
            requestModel(context),
            responseModel(context));
    }

    @Override
    public KeyValues getHighCardinalityKeyValues(ChatModelObservationContext context) {
        List<KeyValue> kept = super.getHighCardinalityKeyValues(context)
            .stream()
            .filter(keyValue -> !TYPED_ON_SPAN.contains(keyValue.getKey()))
            .toList();
        return KeyValues.of(kept.toArray(new KeyValue[0]));
    }
}
