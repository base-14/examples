package com.example.temporaltracing;

import io.opentelemetry.api.OpenTelemetry;
import io.opentelemetry.sdk.OpenTelemetrySdk;
import io.opentelemetry.sdk.trace.SdkTracerProvider;
import io.opentelemetry.sdk.trace.export.BatchSpanProcessor;
import io.opentelemetry.exporter.otlp.trace.OtlpGrpcSpanExporter;
import io.opentelemetry.sdk.resources.Resource;
import io.opentelemetry.context.propagation.ContextPropagators;
import io.opentelemetry.api.trace.propagation.W3CTraceContextPropagator;
import io.opentelemetry.opentracingshim.OpenTracingShim;

import io.temporal.opentracing.OpenTracingOptions;

public final class Tracing {

    private static SdkTracerProvider tracerProvider;

    public static OpenTracingOptions buildTracingOptions() {
        String otlpEndpoint = System.getenv().getOrDefault(
                "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317");
        String serviceName = System.getenv().getOrDefault(
                "OTEL_SERVICE_NAME", "temporal-tracing-example");

        OtlpGrpcSpanExporter spanExporter = OtlpGrpcSpanExporter.builder()
                .setEndpoint(otlpEndpoint)
                .build();

        tracerProvider = SdkTracerProvider.builder()
                .addSpanProcessor(BatchSpanProcessor.builder(spanExporter).build())
                .setResource(Resource.getDefault().toBuilder()
                        .put(io.opentelemetry.semconv.ServiceAttributes.SERVICE_NAME, serviceName)
                        .build())
                .build();

        OpenTelemetry openTelemetry = OpenTelemetrySdk.builder()
                .setTracerProvider(tracerProvider)
                .setPropagators(ContextPropagators.create(
                        W3CTraceContextPropagator.getInstance()))
                .buildAndRegisterGlobal();

        // Flush pending spans on shutdown (SIGTERM from docker compose down, Ctrl+C)
        Runtime.getRuntime().addShutdownHook(new Thread(tracerProvider::shutdown));

        io.opentracing.Tracer tracer = OpenTracingShim.createTracerShim(openTelemetry);

        return OpenTracingOptions.newBuilder()
                .setTracer(tracer)
                .build();
    }

    public static SdkTracerProvider getTracerProvider() {
        return tracerProvider;
    }
}
