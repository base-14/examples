package com.example.support.llm;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import static org.junit.jupiter.api.Assertions.*;

class LlmServiceTest {

    @ParameterizedTest
    @CsvSource({
        "'rate limit exceeded',          rate_limit",
        "'status 429: too many requests', rate_limit",
        "'context deadline exceeded: timeout', timeout",
        "'request timed out',            timeout",
        "'401 unauthorized',             auth_error",
        "'403 forbidden',                auth_error",
        "'authentication failed',        auth_error",
        "'invalid api key',              auth_error",
        "'400 bad request',              invalid_request",
        "'422 unprocessable entity',     invalid_request",
        "'invalid model name',           invalid_request",
        "'500 internal server error',    server_error",
        "'502 bad gateway',              server_error",
        "'503 service unavailable',      server_error",
        "'connection refused',           network_error",
        "'dns resolution failed',        network_error",
        "'connection reset by peer',     network_error",
        "'something unexpected',         unknown_error",
    })
    void classifyErrorCategories(String message, String expected) {
        var error = new RuntimeException(message);
        assertEquals(expected, LlmService.classifyError(error),
            "classifyError(\"" + message + "\") should be " + expected);
    }

    @org.junit.jupiter.api.Test
    void classifyErrorNull() {
        assertEquals("unknown_error", LlmService.classifyError(null));
    }
}
