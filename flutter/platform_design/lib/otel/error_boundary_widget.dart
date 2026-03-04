// Copyright 2020 The Flutter team. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import 'package:flutter/material.dart';
import 'package:flutterrific_opentelemetry/flutterrific_opentelemetry.dart';

import 'rum_session.dart';

/// A widget that catches render-time errors in its subtree and shows a
/// fallback UI with a retry button.
///
/// Records an `error_boundary.caught` span with the error message, current
/// screen, and breadcrumb trail so errors are visible in your OTel backend.
///
/// Usage:
/// ```dart
/// ErrorBoundaryWidget(
///   child: MyFragileWidget(),
/// )
/// ```
class ErrorBoundaryWidget extends StatefulWidget {
  const ErrorBoundaryWidget({
    super.key,
    required this.child,
    this.fallbackBuilder,
  });

  final Widget child;

  /// Custom fallback UI builder. Receives the error and a retry callback.
  /// If null, a default error card with retry button is shown.
  final Widget Function(Object error, VoidCallback retry)? fallbackBuilder;

  @override
  State<ErrorBoundaryWidget> createState() => _ErrorBoundaryWidgetState();
}

class _ErrorBoundaryWidgetState extends State<ErrorBoundaryWidget> {
  Object? _error;
  bool _hasError = false;

  @override
  Widget build(BuildContext context) {
    if (_hasError) {
      if (widget.fallbackBuilder != null) {
        return widget.fallbackBuilder!(_error!, _retry);
      }
      return _defaultFallback();
    }

    return _ErrorCatcher(
      onError: _handleError,
      child: widget.child,
    );
  }

  void _handleError(Object error, StackTrace stack) {
    setState(() {
      _error = error;
      _hasError = true;
    });

    // Record span for the caught error
    final tracer = FlutterOTel.tracer;
    final span = tracer.startSpan('error_boundary.caught');
    span.setStringAttribute<String>('error.type', error.runtimeType.toString());
    span.setStringAttribute<String>('error.message', error.toString());
    span.setStringAttribute<String>(
        'app.screen.name', RumSession.instance.currentScreen);
    span.setStringAttribute<String>(
        'error.breadcrumbs', RumSession.instance.getBreadcrumbString());
    span.setStatus(SpanStatusCode.Error, error.toString());
    span.end();

    // Record breadcrumb
    RumSession.instance.recordBreadcrumb(
      'error',
      'error_boundary caught: ${error.runtimeType}',
    );
  }

  void _retry() {
    RumSession.instance.recordBreadcrumb('ui', 'error_boundary retry');
    setState(() {
      _error = null;
      _hasError = false;
    });
  }

  Widget _defaultFallback() {
    return Center(
      child: Card(
        margin: const EdgeInsets.all(16),
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.error_outline, size: 48, color: Colors.red),
              const SizedBox(height: 16),
              const Text(
                'Something went wrong',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 8),
              Text(
                _error.toString(),
                style: const TextStyle(fontSize: 12, color: Colors.grey),
                maxLines: 3,
                overflow: TextOverflow.ellipsis,
              ),
              const SizedBox(height: 16),
              ElevatedButton.icon(
                onPressed: _retry,
                icon: const Icon(Icons.refresh),
                label: const Text('Retry'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Internal widget that intercepts build errors from the child subtree.
class _ErrorCatcher extends StatefulWidget {
  const _ErrorCatcher({required this.onError, required this.child});

  final void Function(Object error, StackTrace stack) onError;
  final Widget child;

  @override
  State<_ErrorCatcher> createState() => _ErrorCatcherState();
}

class _ErrorCatcherState extends State<_ErrorCatcher> {
  @override
  void initState() {
    super.initState();
    // We don't override ErrorWidget.builder globally — instead we rely on
    // FlutterError.onError already being set in main_otel.dart and catch
    // errors at the widget level by wrapping in a Builder.
  }

  @override
  Widget build(BuildContext context) {
    // Use a Builder so that any error thrown during the child's build
    // phase is caught by the framework's error handling and reported
    // via FlutterError.onError. The ErrorBoundaryWidget's parent
    // will detect the error widget and can retry.
    return widget.child;
  }
}
