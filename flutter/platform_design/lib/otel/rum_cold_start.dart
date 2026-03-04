// Copyright 2020 The Flutter team. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import 'package:flutter/scheduler.dart';
import 'package:flutterrific_opentelemetry/flutterrific_opentelemetry.dart';

import 'rum_session.dart';

/// Measures cold start time — from [main] entry to first frame rendered.
class RumColdStart {
  RumColdStart._();

  static DateTime? _mainStartTime;

  /// Call this as the VERY FIRST line in [main].
  static void markMainStart() {
    _mainStartTime = DateTime.now();
  }

  /// Call after [runApp]. Schedules a post-frame callback to measure total
  /// cold start duration and emit a span + metric.
  static void measureFirstFrame() {
    if (_mainStartTime == null) return;

    SchedulerBinding.instance.addPostFrameCallback((_) {
      final duration = DateTime.now().difference(_mainStartTime!);
      RumSession.instance.coldStartDuration = duration;

      final tracer = FlutterOTel.tracer;
      final span = tracer.startSpan('app.cold_start');
      span.setIntAttribute('app.cold_start_ms', duration.inMilliseconds);
      span.setStringAttribute<String>('app.start_type', 'cold');
      span.end();

      FlutterOTel.meter(name: 'rum.app')
          .createHistogram<double>(
            name: 'app.cold_start_ms',
            unit: 'ms',
            description: 'Time from main() to first frame rendered',
          )
          .record(duration.inMilliseconds.toDouble());
    });
  }
}
