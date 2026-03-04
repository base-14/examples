// Copyright 2020 The Flutter team. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import 'dart:async';
import 'dart:isolate';

// ignore: depend_on_referenced_packages
import 'package:dartastic_opentelemetry_api/dartastic_opentelemetry_api.dart'
    as api;
import 'package:flutter/scheduler.dart';
import 'package:flutterrific_opentelemetry/flutterrific_opentelemetry.dart';

/// Detects frame-level jank and main-thread ANR (Application Not Responding).
///
/// Jank: Uses [SchedulerBinding.addTimingsCallback] to inspect every frame's
/// build and raster durations. Frames exceeding [jankThresholdMs] are recorded
/// as OTel spans and increment a counter.
///
/// ANR: Spawns a background isolate that expects periodic heartbeats from the
/// main isolate. If no heartbeat arrives within [anrThresholdMs], an ANR event
/// is recorded.
class JankDetector {
  JankDetector({
    required UITracer tracer,
    required UIMeter meter,
    this.jankThresholdMs = 16.0,
    this.severeJankThresholdMs = 100.0,
    this.anrThresholdMs = 5000.0,
  })  : _tracer = tracer,
        _meter = meter;

  final UITracer _tracer;
  final UIMeter _meter;
  final double jankThresholdMs;
  final double severeJankThresholdMs;
  final double anrThresholdMs;

  late final api.APICounter<int> _jankCounter;
  late final api.APICounter<int> _severeJankCounter;
  late final api.APICounter<int> _anrCounter;
  late final api.APIHistogram<double> _buildDurationHistogram;
  late final api.APIHistogram<double> _rasterDurationHistogram;

  Isolate? _watchdogIsolate;
  SendPort? _heartbeatPort;
  Timer? _heartbeatTimer;
  ReceivePort? _anrReceivePort;
  bool _paused = false;

  void start() {
    _initMetrics();
    _startFrameTimingCallback();
    _startAnrWatchdog();
  }

  void stop() {
    _heartbeatTimer?.cancel();
    _watchdogIsolate?.kill(priority: Isolate.immediate);
    _anrReceivePort?.close();
  }

  /// Pause heartbeats when app is backgrounded to avoid false ANR alerts.
  void pause() {
    _paused = true;
    _heartbeatTimer?.cancel();
  }

  /// Resume heartbeats when app returns to foreground.
  void resume() {
    _paused = false;
    _startHeartbeats();
  }

  void _initMetrics() {
    _jankCounter = _meter.createCounter<int>(
      name: 'app.jank.count',
      description: 'Number of janky frames (>16ms)',
    );
    _severeJankCounter = _meter.createCounter<int>(
      name: 'app.jank.severe.count',
      description: 'Number of severely janky frames (>100ms)',
    );
    _anrCounter = _meter.createCounter<int>(
      name: 'app.anr.count',
      description: 'Number of ANR events (main thread blocked >5s)',
    );
    _buildDurationHistogram = _meter.createHistogram<double>(
      name: 'app.frame.build_duration_ms',
      unit: 'ms',
      description: 'Frame build phase duration in milliseconds',
    );
    _rasterDurationHistogram = _meter.createHistogram<double>(
      name: 'app.frame.raster_duration_ms',
      unit: 'ms',
      description: 'Frame raster phase duration in milliseconds',
    );
  }

  void _startFrameTimingCallback() {
    SchedulerBinding.instance.addTimingsCallback((timings) {
      for (final timing in timings) {
        final buildMs = timing.buildDuration.inMicroseconds / 1000.0;
        final rasterMs = timing.rasterDuration.inMicroseconds / 1000.0;
        final totalMs = buildMs + rasterMs;

        _buildDurationHistogram.record(buildMs);
        _rasterDurationHistogram.record(rasterMs);

        if (totalMs > jankThresholdMs) {
          _jankCounter.add(1);

          final span = _tracer.startSpan('jank.frame');
          span.setDoubleAttribute('frame.build_duration_ms', buildMs);
          span.setDoubleAttribute('frame.raster_duration_ms', rasterMs);
          span.setDoubleAttribute('frame.total_duration_ms', totalMs);

          if (totalMs > severeJankThresholdMs) {
            _severeJankCounter.add(1);
            span.setStringAttribute<String>('jank.severity', 'severe');
            span.setStatus(SpanStatusCode.Error, 'Severe jank detected');
          } else {
            span.setStringAttribute<String>('jank.severity', 'minor');
          }

          span.end();
        }
      }
    });
  }

  Future<void> _startAnrWatchdog() async {
    _anrReceivePort = ReceivePort();

    _watchdogIsolate = await Isolate.spawn(
      _watchdogEntryPoint,
      _WatchdogConfig(
        mainSendPort: _anrReceivePort!.sendPort,
        anrThresholdMs: anrThresholdMs,
      ),
    );

    _anrReceivePort!.listen((message) {
      if (message is SendPort) {
        _heartbeatPort = message;
        _startHeartbeats();
      } else if (message == 'ANR') {
        _onAnrDetected();
      }
    });
  }

  void _startHeartbeats() {
    _heartbeatTimer?.cancel();
    if (_paused) return;
    _heartbeatTimer = Timer.periodic(
      const Duration(seconds: 1),
      (_) => _heartbeatPort?.send('heartbeat'),
    );
  }

  void _onAnrDetected() {
    _anrCounter.add(1);
    final span = _tracer.startSpan('anr.detected');
    span.setDoubleAttribute('anr.threshold_ms', anrThresholdMs);
    span.setStatus(SpanStatusCode.Error, 'ANR: main thread unresponsive');
    span.end();

    FlutterOTel.reportError(
      'ANR detected: main thread unresponsive for '
      '>${anrThresholdMs.toInt()}ms',
      Exception('ANR detected'),
      StackTrace.current,
    );
  }

  static void _watchdogEntryPoint(_WatchdogConfig config) {
    final receivePort = ReceivePort();
    config.mainSendPort.send(receivePort.sendPort);

    DateTime lastHeartbeat = DateTime.now();

    receivePort.listen((message) {
      if (message == 'heartbeat') {
        lastHeartbeat = DateTime.now();
      }
    });

    Timer.periodic(const Duration(seconds: 1), (_) {
      final elapsed =
          DateTime.now().difference(lastHeartbeat).inMilliseconds;
      if (elapsed > config.anrThresholdMs) {
        config.mainSendPort.send('ANR');
        lastHeartbeat = DateTime.now();
      }
    });
  }
}

class _WatchdogConfig {
  const _WatchdogConfig({
    required this.mainSendPort,
    required this.anrThresholdMs,
  });

  final SendPort mainSendPort;
  final double anrThresholdMs;
}
