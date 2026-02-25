package com.example.support.model;

import java.util.List;

public record IntentResult(
    Intent intent,
    double confidence,
    String subCategory,
    List<String> entities,
    int inputTokens,
    int outputTokens
) {

    public enum Intent { QUERY, ACTION, COMPLAINT, ESCALATE }

    public static IntentResult fallback() {
        return new IntentResult(Intent.QUERY, 0.0, "unknown", List.of(), 0, 0);
    }
}
