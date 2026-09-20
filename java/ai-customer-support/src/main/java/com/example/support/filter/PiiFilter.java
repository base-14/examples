package com.example.support.filter;

import java.util.List;
import java.util.regex.Pattern;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import io.opentelemetry.api.common.Attributes;
import io.opentelemetry.api.common.AttributesBuilder;
import io.opentelemetry.api.trace.Span;

import com.example.support.telemetry.GenAi;

/** Redacts email addresses, phone numbers, SSNs and card numbers from free text. */
@Component
public class PiiFilter {

    private static final Logger log = LoggerFactory.getLogger(PiiFilter.class);
    private static final String REDACTED = "[REDACTED]";
    private static final String EVALUATION_NAME = "pii_scan";

    private record PiiPattern(String name, Pattern pattern) {}

    private static final List<PiiPattern> PATTERNS = List.of(
        new PiiPattern("email",
            Pattern.compile("\\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}\\b")),
        new PiiPattern("ssn",
            Pattern.compile("\\b\\d{3}-\\d{2}-\\d{4}\\b")),
        new PiiPattern("credit_card",
            Pattern.compile("\\b\\d{4}[- ]?\\d{4}[- ]?\\d{4}[- ]?\\d{4}\\b")),
        new PiiPattern("phone",
            Pattern.compile("(?:\\+?1[-.]?)?\\(?\\d{3}\\)?[-.]?\\d{3}[-.]?\\d{4}"))
    );

    public String scrub(String text) {
        if (text == null || text.isEmpty()) {
            return text;
        }
        String result = text;
        for (PiiPattern pii : PATTERNS) {
            var matcher = pii.pattern().matcher(result);
            if (matcher.find()) {
                result = matcher.replaceAll(REDACTED);
            }
        }
        return result;
    }

    /** Scrubs the text and records the result as a GenAI evaluation on the current span. */
    public String evaluate(String text) {
        List<String> detected = detect(text);
        if (!detected.isEmpty()) {
            log.warn("PII detected (types={}), redacting", detected);
        }

        AttributesBuilder attributes = Attributes.builder()
            .put(GenAi.EVALUATION_NAME, EVALUATION_NAME)
            .put(GenAi.EVALUATION_SCORE_VALUE, detected.isEmpty() ? 1.0 : 0.0)
            .put(GenAi.EVALUATION_SCORE_LABEL, detected.isEmpty() ? "pass" : "fail");
        if (!detected.isEmpty()) {
            attributes.put(GenAi.EVALUATION_EXPLANATION, "Redacted " + String.join(", ", detected));
        }
        Span.current().addEvent(GenAi.EVALUATION_RESULT_EVENT, attributes.build());

        return detected.isEmpty() ? text : scrub(text);
    }

    public List<String> detect(String text) {
        if (text == null || text.isEmpty()) {
            return List.of();
        }
        return PATTERNS.stream()
            .filter(pii -> pii.pattern().matcher(text).find())
            .map(PiiPattern::name)
            .toList();
    }

    public boolean containsPii(String text) {
        return !detect(text).isEmpty();
    }
}
