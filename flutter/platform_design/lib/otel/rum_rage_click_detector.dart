// Copyright 2020 The Flutter team. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import 'package:flutterrific_opentelemetry/flutterrific_opentelemetry.dart';

/// Detects rage clicks — rapid repeated taps on the same UI element,
/// indicating user frustration.
///
/// Call [recordClick] on every tap. If 3+ taps on the same element occur
/// within 2 seconds, a `rage_click.detected` span is emitted.
class RumRageClickDetector {
  RumRageClickDetector._();
  static final RumRageClickDetector instance = RumRageClickDetector._();

  static const int _rageThreshold = 3;
  static const Duration _rageWindow = Duration(seconds: 2);

  final Map<String, List<DateTime>> _clickHistory = {};

  /// Record a tap on [elementId]. Returns `true` if rage click was detected.
  bool recordClick(String elementId) {
    final now = DateTime.now();
    final history = _clickHistory.putIfAbsent(elementId, () => []);

    history.removeWhere((t) => now.difference(t) > _rageWindow);
    history.add(now);

    if (history.length >= _rageThreshold) {
      _emitRageClick(elementId, history.length);
      history.clear();
      return true;
    }
    return false;
  }

  void _emitRageClick(String elementId, int clickCount) {
    final tracer = FlutterOTel.tracer;
    final span = tracer.startSpan('rage_click.detected');
    span.setStringAttribute<String>('rage_click.element_id', elementId);
    span.setIntAttribute('rage_click.count', clickCount);
    span.setIntAttribute('rage_click.window_ms', _rageWindow.inMilliseconds);
    span.setStatus(
      SpanStatusCode.Error,
      'Rage click detected on $elementId',
    );
    span.end();

    FlutterOTel.meter(name: 'rum.interaction')
        .createCounter<int>(
          name: 'rage_click.count',
          description: 'Number of rage click events detected',
        )
        .add(1);
  }
}
