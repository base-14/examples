package com.example.support.telemetry;

import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;

import org.springframework.ai.tool.observation.DefaultToolCallingObservationConvention;
import org.springframework.ai.tool.observation.ToolCallingObservationContext;
import org.springframework.stereotype.Component;

/**
 * Spring AI's tool convention without {@code gen_ai.system}. The GenAI tool attributes
 * are set as typed span attributes by {@link GenAiTracingObservationHandler}.
 */
@Component
public class GenAiToolObservationConvention extends DefaultToolCallingObservationConvention {

    @Override
    public KeyValues getLowCardinalityKeyValues(ToolCallingObservationContext context) {
        return KeyValues.of(
            KeyValue.of(GenAi.OPERATION_NAME, context.getOperationMetadata().operationType()),
            springAiKind(context),
            toolType(context),
            toolDefinitionName(context));
    }
}
