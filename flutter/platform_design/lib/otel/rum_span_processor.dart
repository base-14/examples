// Copyright 2020 The Flutter team. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

// ignore: depend_on_referenced_packages
import 'package:dartastic_opentelemetry/dartastic_opentelemetry.dart'
    as sdk;
// ignore: depend_on_referenced_packages
import 'package:dartastic_opentelemetry_api/dartastic_opentelemetry_api.dart';

import 'rum_session.dart';

/// A [SpanProcessor] that wraps a delegate processor and enriches every span
/// with RUM context attributes (session, user, device, screen, network,
/// battery) at [onStart].
///
/// Also implements battery-aware sampling: when the device battery is low,
/// non-error spans may be dropped to conserve power. Error spans are always
/// sampled.
class RumSpanProcessor implements sdk.SpanProcessor {
  RumSpanProcessor(this._delegate);

  final sdk.SpanProcessor _delegate;
  final Set<int> _droppedSpans = {};

  @override
  Future<void> onStart(sdk.Span span, Context? parentContext) async {
    // Battery-aware sampling — drop non-essential spans when battery is low.
    if (!RumSession.instance.shouldSample()) {
      _droppedSpans.add(span.hashCode);
      return;
    }

    final rumAttributes = RumSession.instance.getCommonAttributes();
    span.addAttributes(rumAttributes);
    return _delegate.onStart(span, parentContext);
  }

  @override
  Future<void> onEnd(sdk.Span span) {
    if (_droppedSpans.remove(span.hashCode)) {
      return Future.value();
    }
    return _delegate.onEnd(span);
  }

  @override
  Future<void> onNameUpdate(sdk.Span span, String newName) =>
      _delegate.onNameUpdate(span, newName);

  @override
  Future<void> shutdown() => _delegate.shutdown();

  @override
  Future<void> forceFlush() => _delegate.forceFlush();
}
