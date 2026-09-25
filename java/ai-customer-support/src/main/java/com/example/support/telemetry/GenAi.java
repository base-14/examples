package com.example.support.telemetry;

/** Attribute, metric and event names from the OTel GenAI semantic conventions. */
public final class GenAi {

    public static final String OPERATION_NAME = "gen_ai.operation.name";
    public static final String PROVIDER_NAME = "gen_ai.provider.name";
    public static final String REQUEST_MODEL = "gen_ai.request.model";
    public static final String RESPONSE_MODEL = "gen_ai.response.model";
    public static final String RESPONSE_FINISH_REASONS = "gen_ai.response.finish_reasons";
    public static final String USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens";
    public static final String USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens";
    public static final String CONVERSATION_ID = "gen_ai.conversation.id";
    public static final String AGENT_NAME = "gen_ai.agent.name";
    public static final String TOOL_NAME = "gen_ai.tool.name";
    public static final String TOOL_CALL_ID = "gen_ai.tool.call.id";
    public static final String TOOL_CALL_ARGUMENTS = "gen_ai.tool.call.arguments";
    public static final String TOOL_CALL_RESULT = "gen_ai.tool.call.result";
    public static final String DATA_SOURCE_ID = "gen_ai.data_source.id";

    public static final String INPUT_MESSAGES = "gen_ai.input.messages";
    public static final String OUTPUT_MESSAGES = "gen_ai.output.messages";
    public static final String SYSTEM_INSTRUCTIONS = "gen_ai.system_instructions";
    public static final String INFERENCE_DETAILS_EVENT = "gen_ai.client.inference.operation.details";

    public static final String EVALUATION_RESULT_EVENT = "gen_ai.evaluation.result";
    public static final String EVALUATION_NAME = "gen_ai.evaluation.name";
    public static final String EVALUATION_SCORE_VALUE = "gen_ai.evaluation.score.value";
    public static final String EVALUATION_SCORE_LABEL = "gen_ai.evaluation.score.label";
    public static final String EVALUATION_EXPLANATION = "gen_ai.evaluation.explanation";

    public static final String COST_USD = "base14.gen_ai.cost_usd";
    public static final String FALLBACK_PROVIDER = "base14.gen_ai.fallback.provider";
    public static final String FALLBACK_TRIGGERED = "gen_ai.fallback.triggered";
    // Not base14.gen_ai.retry.attempt: _shared/test-vectors/chat-with-retry.json fixes this name.
    public static final String RETRY_ATTEMPT = "base14.retry.attempt";

    public static final String ERROR_TYPE = "error.type";
    public static final String SERVER_ADDRESS = "server.address";
    public static final String SERVER_PORT = "server.port";

    public static final String COST_METRIC = "base14.gen_ai.cost";
    public static final String RETRY_METRIC = "base14.gen_ai.retry.count";
    public static final String FALLBACK_METRIC = "base14.gen_ai.fallback.count";
    public static final String ERROR_METRIC = "base14.gen_ai.error.count";
    public static final String OPERATION_DURATION_METRIC = "gen_ai.client.operation.duration";

    public static final String FALLBACK_EVENT = "provider_fallback";
    public static final String TOOL_FAILED_EVENT = "tool_execution_failed";
    public static final String RETRIEVAL_DEGRADED_EVENT = "rag_retrieval_degraded";
    public static final String TOOL_LOOP_LIMIT_EVENT = "tool_loop_limit_reached";
    public static final String TOOL_LOOP_ROUNDS = "base14.tool.rounds";

    private GenAi() {
    }
}
