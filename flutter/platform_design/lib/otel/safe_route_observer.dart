// Copyright 2020 The Flutter team. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import 'package:flutter/widgets.dart';
import 'package:flutterrific_opentelemetry/flutterrific_opentelemetry.dart';

/// Wraps [OTelNavigatorObserver] to handle apps that use imperative
/// navigation (Navigator.push) instead of page-based routing (go_router).
///
/// The upstream observer assumes `route.settings` is a `Page<dynamic>`,
/// which crashes with a cast error on imperative routes. This wrapper
/// catches that and records a manual span instead.
class SafeRouteObserver extends NavigatorObserver {
  SafeRouteObserver();

  final _tracer = FlutterOTel.tracer;

  @override
  void didPush(Route<dynamic> route, Route<dynamic>? previousRoute) {
    _recordRouteChange('push', route, previousRoute);
  }

  @override
  void didPop(Route<dynamic> route, Route<dynamic>? previousRoute) {
    _recordRouteChange('pop', route, previousRoute);
  }

  @override
  void didReplace({Route<dynamic>? newRoute, Route<dynamic>? oldRoute}) {
    _recordRouteChange('replace', newRoute, oldRoute);
  }

  @override
  void didRemove(Route<dynamic> route, Route<dynamic>? previousRoute) {
    _recordRouteChange('remove', route, previousRoute);
  }

  void _recordRouteChange(
    String action,
    Route<dynamic>? route,
    Route<dynamic>? previousRoute,
  ) {
    final routeName = route?.settings.name ?? 'unknown';
    final previousName = previousRoute?.settings.name;

    final span = _tracer.startSpan('navigation.$action');
    span.setStringAttribute<String>('nav.action', action);
    span.setStringAttribute<String>('nav.route', routeName);
    if (previousName != null) {
      span.setStringAttribute<String>('nav.previous_route', previousName);
    }
    span.end();
  }
}
