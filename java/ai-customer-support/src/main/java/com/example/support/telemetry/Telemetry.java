package com.example.support.telemetry;

import io.opentelemetry.api.OpenTelemetry;
import io.opentelemetry.api.metrics.Meter;
import io.opentelemetry.api.trace.Tracer;

import org.springframework.stereotype.Component;

/** The tracer and meter every instrumented component in this app writes to. */
@Component
public class Telemetry {

    private static final String SCOPE = "ai-customer-support";

    private final Tracer tracer;
    private final Meter meter;

    public Telemetry(OpenTelemetry openTelemetry) {
        this.tracer = openTelemetry.getTracer(SCOPE);
        this.meter = openTelemetry.getMeter(SCOPE);
    }

    public Tracer tracer() {
        return tracer;
    }

    public Meter meter() {
        return meter;
    }
}
