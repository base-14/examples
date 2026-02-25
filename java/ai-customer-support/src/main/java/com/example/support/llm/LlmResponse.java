package com.example.support.llm;

public record LlmResponse(
    String content,
    String model,
    String provider,
    int inputTokens,
    int outputTokens,
    double costUsd,
    String finishReason
) {}
