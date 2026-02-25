package com.example.support.filter;

import java.util.List;
import java.util.regex.Pattern;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import io.opentelemetry.api.GlobalOpenTelemetry;
import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.api.common.Attributes;
import io.opentelemetry.api.trace.Span;

@Component
public class PiiFilter {

    private static final Logger log = LoggerFactory.getLogger(PiiFilter.class);
    private static final String REDACTED = "[REDACTED]";

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
        if (text == null || text.isEmpty()) return text;

        String result = text;
        boolean piiFound = false;

        for (var pii : PATTERNS) {
            var matcher = pii.pattern().matcher(result);
            if (matcher.find()) {
                piiFound = true;
                log.warn("PII detected (type={}), redacting", pii.name());
                result = matcher.replaceAll(REDACTED);
            }
        }

        if (piiFound) {
            Span current = Span.current();
            current.addEvent("support.pii_detected", Attributes.of(
                AttributeKey.booleanKey("support.pii_redacted"), true
            ));
        }

        return result;
    }

    public boolean containsPii(String text) {
        if (text == null || text.isEmpty()) return false;
        return PATTERNS.stream().anyMatch(p -> p.pattern().matcher(text).find());
    }
}
