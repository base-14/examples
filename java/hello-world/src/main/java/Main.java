// Java Hello World — OpenTelemetry

import io.opentelemetry.api.OpenTelemetry;
import io.opentelemetry.api.common.Attributes;
import io.opentelemetry.api.logs.Logger;
import io.opentelemetry.api.logs.Severity;
import io.opentelemetry.api.metrics.LongCounter;
import io.opentelemetry.api.metrics.Meter;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.exporter.otlp.http.logs.OtlpHttpLogRecordExporter;
import io.opentelemetry.exporter.otlp.http.metrics.OtlpHttpMetricExporter;
import io.opentelemetry.exporter.otlp.http.trace.OtlpHttpSpanExporter;
import io.opentelemetry.sdk.OpenTelemetrySdk;
import io.opentelemetry.sdk.logs.SdkLoggerProvider;
import io.opentelemetry.sdk.logs.export.BatchLogRecordProcessor;
import io.opentelemetry.sdk.metrics.SdkMeterProvider;
import io.opentelemetry.sdk.metrics.export.PeriodicMetricReader;
import io.opentelemetry.sdk.resources.Resource;
import io.opentelemetry.sdk.trace.SdkTracerProvider;
import io.opentelemetry.sdk.trace.export.BatchSpanProcessor;
import io.opentelemetry.api.common.AttributeKey;

import java.time.Duration;

public class Main {

    public static void main(String[] args) {
        // -- Configuration ------------------------------------------------------
        // The collector endpoint. Set this to where your OTel collector accepts
        // OTLP/HTTP traffic (default port 4318).
        String endpoint = System.getenv("OTEL_EXPORTER_OTLP_ENDPOINT");
        if (endpoint == null || endpoint.isEmpty()) {
            System.err.println("Set OTEL_EXPORTER_OTLP_ENDPOINT (e.g. http://localhost:4318)");
            System.exit(1);
        }

        // A Resource identifies your application in the telemetry backend.
        // Every span, log, and metric carries this identity.
        // Java's default Resource only includes telemetry.sdk.* — we add
        // process and OS attributes from JVM system properties.
        Resource resource = Resource.getDefault().merge(Resource.create(Attributes.builder()
                .put("service.name", "hello-world-java")
                .put("process.runtime.name", System.getProperty("java.runtime.name", ""))
                .put("process.runtime.version", System.getProperty("java.runtime.version", ""))
                .put(AttributeKey.longKey("process.pid"), ProcessHandle.current().pid())
                .put("os.type", System.getProperty("os.name", ""))
                .put("os.version", System.getProperty("os.version", ""))
                .put("host.arch", System.getProperty("os.arch", ""))
                .build()));

        // -- Traces -------------------------------------------------------------
        // A TracerProvider manages the lifecycle of traces. It batches spans and
        // sends them to the collector via the OTLP/HTTP exporter.
        SdkTracerProvider tracerProvider = SdkTracerProvider.builder()
                .setResource(resource)
                .addSpanProcessor(BatchSpanProcessor.builder(
                        OtlpHttpSpanExporter.builder().setEndpoint(endpoint + "/v1/traces").build()
                ).build())
                .build();

        // -- Logs ---------------------------------------------------------------
        // A LoggerProvider sends structured logs to the collector. Logs emitted
        // inside a span automatically carry the span's trace ID and span ID —
        // this is called log-trace correlation.
        SdkLoggerProvider loggerProvider = SdkLoggerProvider.builder()
                .setResource(resource)
                .addLogRecordProcessor(BatchLogRecordProcessor.builder(
                        OtlpHttpLogRecordExporter.builder().setEndpoint(endpoint + "/v1/logs").build()
                ).build())
                .build();

        // -- Metrics ------------------------------------------------------------
        // A MeterProvider manages metrics. The PeriodicMetricReader collects and
        // exports metric data at regular intervals.
        SdkMeterProvider meterProvider = SdkMeterProvider.builder()
                .setResource(resource)
                .registerMetricReader(PeriodicMetricReader.builder(
                        OtlpHttpMetricExporter.builder().setEndpoint(endpoint + "/v1/metrics").build()
                ).setInterval(Duration.ofSeconds(5)).build())
                .build();

        OpenTelemetry otel = OpenTelemetrySdk.builder()
                .setTracerProvider(tracerProvider)
                .setLoggerProvider(loggerProvider)
                .setMeterProvider(meterProvider)
                .build();

        Tracer tracer = otel.getTracer("hello-world-java");
        Logger logger = otel.getLogsBridge().get("hello-world-java");
        Meter meter = otel.getMeter("hello-world-java");

        // A counter tracks how many times something happens.
        LongCounter helloCounter = meter.counterBuilder("hello.count")
                .setDescription("Number of times the hello-world app has run")
                .build();

        // -- Run ----------------------------------------------------------------
        sayHello(tracer, logger, helloCounter);
        checkDiskSpace(tracer, logger);
        parseConfig(tracer, logger);

        // -- Shutdown -----------------------------------------------------------
        // Flush all buffered telemetry to the collector before exiting.
        // Without this, the last batch of spans/logs/metrics may be lost.
        tracerProvider.close();
        loggerProvider.close();
        meterProvider.close();

        System.out.println("Done. Check Scout for your trace, log, and metric.");
    }

    // A normal operation — creates a span with an info log.
    static void sayHello(Tracer tracer, Logger logger, LongCounter counter) {
        // A span represents a unit of work.
        Span span = tracer.spanBuilder("say-hello").startSpan();
        try (var scope = span.makeCurrent()) {
            // This log is emitted inside the span, so it carries the span's trace ID.
            // In Scout, you can jump to the trace from a log detail.
            logger.logRecordBuilder()
                    .setSeverity(Severity.INFO)
                    .setSeverityText("INFO")
                    .setBody("Hello, World!")
                    .emit();
            counter.add(1);
            span.setAttribute("greeting", "Hello, World!");
        } finally {
            span.end();
        }
    }

    // A degraded operation — creates a span with a warning log.
    static void checkDiskSpace(Tracer tracer, Logger logger) {
        Span span = tracer.spanBuilder("check-disk-space").startSpan();
        try (var scope = span.makeCurrent()) {
            // Warnings show up in Scout with a distinct severity level, making
            // them easy to filter and spot before they become errors.
            logger.logRecordBuilder()
                    .setSeverity(Severity.WARN)
                    .setSeverityText("WARN")
                    .setBody("Disk usage above 90%")
                    .emit();
            span.setAttribute("disk.usage_percent", 92);
        } finally {
            span.end();
        }
    }

    // A failed operation — creates a span with an error and exception.
    static void parseConfig(Tracer tracer, Logger logger) {
        Span span = tracer.spanBuilder("parse-config").startSpan();
        try (var scope = span.makeCurrent()) {
            RuntimeException error = new RuntimeException("invalid config: missing 'database_url'");
            // recordException attaches the stack trace to the span.
            // setStatus marks the span as errored so it stands out in TraceX.
            span.recordException(error);
            span.setStatus(StatusCode.ERROR, error.getMessage());
            logger.logRecordBuilder()
                    .setSeverity(Severity.ERROR)
                    .setSeverityText("ERROR")
                    .setBody("Failed to parse configuration: " + error.getMessage())
                    .emit();
        } finally {
            span.end();
        }
    }
}
