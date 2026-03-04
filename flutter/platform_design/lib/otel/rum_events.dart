// Copyright 2020 The Flutter team. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import 'package:flutterrific_opentelemetry/flutterrific_opentelemetry.dart';

/// Simple custom event API for business events.
///
/// RUM context (session, user, screen, device) is automatically attached
/// to every event by [RumSpanProcessor].
class RumEvents {
  RumEvents._();

  /// Log a custom business event as a span.
  static void logEvent(String name, {Map<String, Object>? attributes}) {
    final tracer = FlutterOTel.tracer;
    final span = tracer.startSpan('custom_event.$name');
    span.setStringAttribute<String>('event.name', name);
    span.setStringAttribute<String>('event.domain', 'business');
    if (attributes != null) {
      for (final entry in attributes.entries) {
        final value = entry.value;
        if (value is String) {
          span.setStringAttribute<String>(entry.key, value);
        } else if (value is int) {
          span.setIntAttribute(entry.key, value);
        } else if (value is double) {
          span.setDoubleAttribute(entry.key, value);
        }
      }
    }
    span.end();
  }

  /// Log an event with a measured duration.
  static void logTimedEvent(
    String name,
    Duration duration, {
    Map<String, Object>? attributes,
  }) {
    final allAttrs = <String, Object>{
      'event.duration_ms': duration.inMilliseconds,
      ...?attributes,
    };
    logEvent(name, attributes: allAttrs);
  }
}
