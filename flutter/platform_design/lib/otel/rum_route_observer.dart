// Copyright 2020 The Flutter team. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import 'package:flutter/scheduler.dart';
import 'package:flutter/widgets.dart';
import 'package:flutterrific_opentelemetry/flutterrific_opentelemetry.dart';

import 'rum_session.dart';

/// Enhanced route observer with screen load time and dwell time tracking.
///
/// Replaces [SafeRouteObserver]. For each navigation event:
/// - Records a `navigation.<action>` span with route names
/// - Tracks **screen dwell time** via long-lived `screen.dwell.<route>` spans
/// - Measures **screen load time** (push → first frame) as `screen.load.<route>`
/// - Updates [RumSession.currentScreen] so all spans reflect the active screen
class RumRouteObserver extends NavigatorObserver {
  final _tracer = FlutterOTel.tracer;
  final Map<String, DateTime> _screenPushTimes = {};
  final Map<String, DateTime> _dwellStartTimes = {};

  @override
  void didPush(Route<dynamic> route, Route<dynamic>? previousRoute) {
    final routeName = route.settings.name ?? 'unknown';
    final previousName = previousRoute?.settings.name;

    // End dwell tracking for previous screen
    _endDwellSpan(previousName);

    // Update RUM session current screen
    RumSession.instance.setCurrentScreen(routeName);

    // Record breadcrumb
    RumSession.instance.recordBreadcrumb('navigation', 'push $routeName');

    // Record push time for load time measurement
    _screenPushTimes[routeName] = DateTime.now();

    // Record navigation span
    final span = _tracer.startSpan('navigation.push');
    span.setStringAttribute<String>('app.navigation.action', 'push');
    span.setStringAttribute<String>('app.screen.name', routeName);
    if (previousName != null) {
      span.setStringAttribute<String>('app.screen.previous_name', previousName);
    }
    span.end();

    // Start dwell tracking for new screen
    _startDwellTracking(routeName);

    // Measure screen load time after next frame renders
    SchedulerBinding.instance.addPostFrameCallback((_) {
      _recordScreenLoadTime(routeName);
    });
  }

  @override
  void didPop(Route<dynamic> route, Route<dynamic>? previousRoute) {
    final routeName = route.settings.name ?? 'unknown';
    final previousName = previousRoute?.settings.name;

    // End dwell for popped screen
    _endDwellSpan(routeName);
    _screenPushTimes.remove(routeName);

    // Record breadcrumb
    RumSession.instance.recordBreadcrumb('navigation', 'pop $routeName');

    // Resume dwell for screen being returned to
    if (previousName != null) {
      RumSession.instance.setCurrentScreen(previousName);
      _startDwellTracking(previousName);
    }

    final span = _tracer.startSpan('navigation.pop');
    span.setStringAttribute<String>('app.navigation.action', 'pop');
    span.setStringAttribute<String>('app.screen.name', routeName);
    if (previousName != null) {
      span.setStringAttribute<String>('app.screen.previous_name', previousName);
    }
    span.end();
  }

  @override
  void didReplace({Route<dynamic>? newRoute, Route<dynamic>? oldRoute}) {
    final oldName = oldRoute?.settings.name;
    final newName = newRoute?.settings.name ?? 'unknown';

    _endDwellSpan(oldName);
    RumSession.instance.setCurrentScreen(newName);
    _startDwellTracking(newName);

    // Record breadcrumb
    RumSession.instance.recordBreadcrumb('navigation', 'replace to $newName');

    final span = _tracer.startSpan('navigation.replace');
    span.setStringAttribute<String>('app.navigation.action', 'replace');
    span.setStringAttribute<String>('nav.route', newName);
    if (oldName != null) {
      span.setStringAttribute<String>('nav.previous_route', oldName);
    }
    span.end();
  }

  @override
  void didRemove(Route<dynamic> route, Route<dynamic>? previousRoute) {
    final routeName = route.settings.name ?? 'unknown';
    _endDwellSpan(routeName);

    final span = _tracer.startSpan('navigation.remove');
    span.setStringAttribute<String>('app.navigation.action', 'remove');
    span.setStringAttribute<String>('app.screen.name', routeName);
    span.end();
  }

  void _startDwellTracking(String routeName) {
    _dwellStartTimes[routeName] = DateTime.now();
  }

  void _endDwellSpan(String? routeName) {
    if (routeName == null) return;
    final startTime = _dwellStartTimes.remove(routeName);
    if (startTime == null) return;

    final dwellMs = DateTime.now().difference(startTime).inMilliseconds;

    final span = _tracer.startSpan('screen.dwell');
    span.setStringAttribute<String>('app.screen.name', routeName);
    span.setIntAttribute('app.screen.dwell_time_ms', dwellMs);
    span.end();

    FlutterOTel.meter(name: 'rum.screen')
        .createHistogram<double>(
          name: 'screen.dwell_time_ms',
          unit: 'ms',
          description: 'Time user spent on screen',
        )
        .record(dwellMs.toDouble());
  }

  void _recordScreenLoadTime(String routeName) {
    final pushTime = _screenPushTimes[routeName];
    if (pushTime == null) return;

    final loadMs = DateTime.now().difference(pushTime).inMilliseconds;

    final span = _tracer.startSpan('screen.load');
    span.setStringAttribute<String>('app.screen.name', routeName);
    span.setIntAttribute('app.screen.load_time_ms', loadMs);
    span.end();

    FlutterOTel.meter(name: 'rum.screen')
        .createHistogram<double>(
          name: 'screen.load_time_ms',
          unit: 'ms',
          description: 'Time from navigation push to first frame rendered',
        )
        .record(loadMs.toDouble());
  }
}
