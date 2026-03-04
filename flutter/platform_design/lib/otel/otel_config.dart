// Copyright 2020 The Flutter team. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import 'package:flutter/widgets.dart';
import 'package:flutterrific_opentelemetry/flutterrific_opentelemetry.dart';

import 'jank_detector.dart';
import 'rum_http_client.dart';
import 'rum_route_observer.dart';
import 'rum_session.dart';
import 'rum_span_processor.dart';

/// Centralizes all OpenTelemetry + RUM initialization for the app.
class OTelConfig {
  OTelConfig._();

  static JankDetector? _jankDetector;
  static RumHttpClient? _httpClient;
  static RumSpanProcessor? _rumProcessor;

  /// Call once before runApp().
  ///
  /// Uses OTLP/HTTP on localhost:24318 for traces and gRPC on localhost:24317
  /// for metrics by default. Override via --dart-define.
  static Future<void> initialize() async {
    WidgetsFlutterBinding.ensureInitialized();

    const traceEndpoint = String.fromEnvironment(
      'OTEL_TRACE_ENDPOINT',
      defaultValue: 'http://localhost:24318',
    );
    const metricEndpoint = String.fromEnvironment(
      'OTEL_METRIC_ENDPOINT',
      defaultValue: 'http://localhost:24317',
    );

    // Initialize RUM session FIRST (before FlutterOTel, because
    // FlutterOTel.initialize creates lifecycle spans that trigger
    // RumSpanProcessor which needs RumSession to be ready).
    await RumSession.instance.initialize();

    // HTTP for traces, gRPC for metrics (HTTP metric exporter has a
    // frozen-protobuf bug in dartastic v0.8.6).
    final spanExporter = OtlpHttpSpanExporter(
      OtlpHttpExporterConfig(endpoint: traceEndpoint),
    );
    final batchProcessor = BatchSpanProcessor(spanExporter);

    // Wrap in RumSpanProcessor to enrich ALL spans with RUM context
    // (session, user, device, screen, network).
    _rumProcessor = RumSpanProcessor(batchProcessor);
    final rumProcessor = _rumProcessor!;

    final metricExporter = OtlpGrpcMetricExporter(
      OtlpGrpcMetricExporterConfig(
        endpoint: metricEndpoint,
        insecure: true,
      ),
    );

    await FlutterOTel.initialize(
      serviceName: 'platform-design-app',
      serviceVersion: '1.0.0',
      tracerName: 'platform-design',
      spanProcessor: rumProcessor,
      metricExporter: metricExporter,
      enableMetrics: true,
      secure: false,
    );

    // Start jank/ANR detection.
    _jankDetector = JankDetector(
      tracer: FlutterOTel.tracer,
      meter: FlutterOTel.meter(name: 'jank_detector'),
    );
    _jankDetector!.start();

    // Create instrumented HTTP client.
    _httpClient = RumHttpClient();
  }

  /// Route observer with screen load time + dwell time tracking.
  static RumRouteObserver get routeObserver => RumRouteObserver();

  static OTelLifecycleObserver get lifecycleObserver =>
      FlutterOTel.lifecycleObserver;

  static OTelInteractionTracker get interactionTracker =>
      FlutterOTel.interactionTracker;

  /// Instrumented HTTP client for network request tracing.
  static RumHttpClient get httpClient => _httpClient ?? RumHttpClient();

  /// Pause jank detection when app is backgrounded.
  static void pauseJankDetection() => _jankDetector?.pause();

  /// Resume jank detection when app returns to foreground.
  static void resumeJankDetection() => _jankDetector?.resume();

  /// Force-flush all pending spans to the collector.
  static Future<void> flush() async {
    await _rumProcessor?.forceFlush();
  }

  /// Flush and shut down the span processor.
  static Future<void> shutdown() async {
    await flush();
    await _rumProcessor?.shutdown();
  }

  static void dispose() {
    _jankDetector?.stop();
    _httpClient?.close();
    RumSession.instance.dispose();
  }
}
