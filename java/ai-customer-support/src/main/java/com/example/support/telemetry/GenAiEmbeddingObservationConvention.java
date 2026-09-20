package com.example.support.telemetry;

import java.util.Optional;

import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;

import org.springframework.ai.embedding.EmbeddingOptions;
import org.springframework.ai.embedding.observation.DefaultEmbeddingModelObservationConvention;
import org.springframework.ai.embedding.observation.EmbeddingModelObservationContext;
import org.springframework.stereotype.Component;

/**
 * Spring AI's embedding convention renamed to the semconv operation {@code embeddings},
 * with {@code gen_ai.system} replaced by {@code gen_ai.provider.name}.
 */
@Component
public class GenAiEmbeddingObservationConvention extends DefaultEmbeddingModelObservationConvention {

    private static final String OPERATION = "embeddings";

    @Override
    public String getContextualName(EmbeddingModelObservationContext context) {
        return Optional.ofNullable(context.getRequest().getOptions())
            .map(EmbeddingOptions::getModel)
            .filter(model -> !model.isBlank())
            .map(model -> OPERATION + " " + model)
            .orElse(OPERATION);
    }

    @Override
    public KeyValues getLowCardinalityKeyValues(EmbeddingModelObservationContext context) {
        return KeyValues.of(
            KeyValue.of(GenAi.OPERATION_NAME, OPERATION),
            KeyValue.of(GenAi.PROVIDER_NAME, context.getOperationMetadata().provider()),
            requestModel(context),
            responseModel(context));
    }
}
