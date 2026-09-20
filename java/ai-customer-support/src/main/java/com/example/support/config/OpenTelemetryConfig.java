package com.example.support.config;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.config.MeterFilter;
import io.micrometer.tracing.Tracer;
import io.micrometer.tracing.otel.bridge.OtelCurrentTraceContext;
import io.micrometer.tracing.otel.bridge.OtelTracer;
import io.opentelemetry.api.GlobalOpenTelemetry;
import io.opentelemetry.api.OpenTelemetry;
import io.opentelemetry.instrumentation.micrometer.v1_5.OpenTelemetryMeterRegistry;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Binds the application to the OpenTelemetry Java agent. The agent owns the SDK and is
 * the only exporter, so the app carries no SDK on its classpath. Spring Boot's tracing
 * auto-configuration needs that SDK to build its own tracer, so it backs off and the
 * Micrometer tracer is built here over the agent's global instance instead.
 */
@Configuration
public class OpenTelemetryConfig {

    private static final String SCOPE = "ai-customer-support";

    @Bean
    OpenTelemetry openTelemetry() {
        return GlobalOpenTelemetry.get();
    }

    /**
     * Micrometer meters, including Spring AI's token usage, reach the collector through
     * this registry. The agent's own JVM and process metrics are denied here so they are
     * not reported twice under the same names.
     */
    @Bean
    MeterRegistry meterRegistry(OpenTelemetry openTelemetry) {
        MeterRegistry registry = OpenTelemetryMeterRegistry.builder(openTelemetry).build();
        registry.config().meterFilter(MeterFilter.deny(id ->
            id.getName().startsWith("jvm.")
                || id.getName().startsWith("process.")
                || id.getName().startsWith("system.")
                || id.getName().startsWith("disk.")));
        return registry;
    }

    @Bean
    OtelCurrentTraceContext otelCurrentTraceContext() {
        return new OtelCurrentTraceContext();
    }

    @Bean
    Tracer micrometerTracer(OpenTelemetry openTelemetry, OtelCurrentTraceContext currentTraceContext) {
        return new OtelTracer(openTelemetry.getTracer(SCOPE), currentTraceContext, event -> { });
    }
}
