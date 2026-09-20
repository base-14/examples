package com.example.support.telemetry;

import java.util.List;

import io.opentelemetry.sdk.OpenTelemetrySdk;
import io.opentelemetry.sdk.metrics.SdkMeterProvider;
import io.opentelemetry.sdk.metrics.data.MetricData;
import io.opentelemetry.sdk.testing.exporter.InMemoryMetricReader;
import io.opentelemetry.sdk.testing.exporter.InMemorySpanExporter;
import io.opentelemetry.sdk.trace.SdkTracerProvider;
import io.opentelemetry.sdk.trace.data.SpanData;
import io.opentelemetry.sdk.trace.export.SimpleSpanProcessor;

/** An OpenTelemetry SDK that keeps its spans and metrics in memory, for assertions. */
public final class TestOtel implements AutoCloseable {

    private final InMemorySpanExporter spanExporter = InMemorySpanExporter.create();
    private final InMemoryMetricReader metricReader = InMemoryMetricReader.create();
    private final OpenTelemetrySdk sdk;

    public TestOtel() {
        this.sdk = OpenTelemetrySdk.builder()
            .setTracerProvider(SdkTracerProvider.builder()
                .addSpanProcessor(SimpleSpanProcessor.create(spanExporter))
                .build())
            .setMeterProvider(SdkMeterProvider.builder()
                .registerMetricReader(metricReader)
                .build())
            .build();
    }

    public OpenTelemetrySdk sdk() {
        return sdk;
    }

    public Telemetry telemetry() {
        return new Telemetry(sdk);
    }

    public List<SpanData> spans() {
        return spanExporter.getFinishedSpanItems();
    }

    public List<MetricData> metrics() {
        return List.copyOf(metricReader.collectAllMetrics());
    }

    @Override
    public void close() {
        sdk.close();
    }
}
