import 'package:flutter/foundation.dart';

import 'log_service.dart';
import 'metrics_service.dart';
import 'telemetry_service.dart';

class ErrorDetails {
  const ErrorDetails({
    required this.error,
    this.stackTrace,
    this.context,
    required this.timestamp,
    this.metadata = const {},
  });

  final String error;
  final String? stackTrace;
  final String? context;
  final DateTime timestamp;
  final Map<String, dynamic> metadata;

  Map<String, dynamic> toJson() => {
    'error': error,
    'stack_trace': stackTrace,
    'context': context,
    'timestamp': timestamp.toIso8601String(),
    'metadata': metadata,
  };
}

class ErrorHandlerService {
  ErrorHandlerService._();

  static ErrorHandlerService? _instance;
  static ErrorHandlerService get instance => _instance ??= ErrorHandlerService._();

  final List<ErrorDetails> _recentErrors = [];
  final int _maxRecentErrors = 50;

  String _currentScreen = 'unknown';
  String _lastUserAction = 'none';
  bool _hasCrashed = false;
  final List<String> _breadcrumbs = [];
  static const int _maxBreadcrumbs = 20;

  void initialize() {
    FlutterError.onError = _handleFlutterError;

    PlatformDispatcher.instance.onError = (error, stack) {
      _handlePlatformError(error, stack);
      return true;
    };

    TelemetryService.instance.recordEvent('error_handler_initialize', attributes: {
      'session_id': TelemetryService.instance.sessionId,
    });
  }

  void setCurrentScreen(String screen) {
    _currentScreen = screen;
  }

  void recordBreadcrumb(String action) {
    _breadcrumbs.add(action);
    if (_breadcrumbs.length > _maxBreadcrumbs) {
      _breadcrumbs.removeAt(0);
    }
    _lastUserAction = action;
  }

  bool get hasCrashed => _hasCrashed;

  void _handleFlutterError(FlutterErrorDetails details) {
    final isCrash = !details.silent;

    final errorDetails = ErrorDetails(
      error: details.exception.toString(),
      stackTrace: details.stack?.toString(),
      context: details.context?.toString(),
      timestamp: DateTime.now(),
      metadata: {
        'error_type': 'flutter_error',
        'library': details.library,
        'silent': details.silent,
      },
    );

    _recordError(errorDetails, isCrash: isCrash);
  }

  void _handlePlatformError(Object error, StackTrace stack) {
    final errorDetails = ErrorDetails(
      error: error.toString(),
      stackTrace: stack.toString(),
      context: 'platform_error',
      timestamp: DateTime.now(),
      metadata: {
        'error_type': 'platform_error',
      },
    );

    _recordError(errorDetails, isCrash: true);
  }

  void recordZoneError(Object error, StackTrace stackTrace) {
    final errorDetails = ErrorDetails(
      error: error.toString(),
      stackTrace: stackTrace.toString(),
      context: 'zone_uncaught',
      timestamp: DateTime.now(),
      metadata: {'error_type': 'zone_uncaught_error'},
    );
    // _recordError with isCrash:true triggers _forceFlushAll internally
    _recordError(errorDetails, isCrash: true);
  }

  void recordCustomError(
    String error, {
    String? stackTrace,
    String? context,
    Map<String, dynamic>? metadata,
  }) {
    final errorDetails = ErrorDetails(
      error: error,
      stackTrace: stackTrace,
      context: context,
      timestamp: DateTime.now(),
      metadata: {
        'error_type': 'custom_error',
        ...?metadata,
      },
    );

    _recordError(errorDetails);
  }

  void _recordError(ErrorDetails errorDetails, {bool isCrash = false}) {
    _recentErrors.insert(0, errorDetails);
    if (_recentErrors.length > _maxRecentErrors) {
      _recentErrors.removeLast();
    }

    final severity = isCrash ? 'crash' : 'error';
    if (isCrash) _hasCrashed = true;

    final attrs = <String, Object>{
      'error.message': errorDetails.error,
      'error.context': errorDetails.context ?? 'unknown',
      'error.type': (errorDetails.metadata['error_type'] as String?) ?? 'unknown',
      'error.severity': severity,
      'error.is_fatal': isCrash,
      'session.id': TelemetryService.instance.sessionId,
      'session.duration_ms': DateTime.now().difference(TelemetryService.instance.sessionStartTime).inMilliseconds,
      'screen.current': _currentScreen,
      'user.last_action': _lastUserAction,
      'breadcrumbs': _breadcrumbs.join(' > '),
      'has_stack_trace': errorDetails.stackTrace != null,
    };

    TelemetryService.instance.recordEvent('error_occurred', attributes: attrs);

    final logAttrs = attrs.map((k, v) => MapEntry(k, v.toString()));
    if (isCrash) {
      LogService.instance.fatal(
        errorDetails.error,
        exception: errorDetails.error,
        stackTrace: errorDetails.stackTrace != null ? StackTrace.fromString(errorDetails.stackTrace!) : null,
        attributes: logAttrs,
      );
    } else {
      LogService.instance.error(
        errorDetails.error,
        stackTrace: errorDetails.stackTrace != null ? StackTrace.fromString(errorDetails.stackTrace!) : null,
        attributes: logAttrs,
      );
    }

    MetricsService.instance.incrementCounter(
      isCrash ? 'app.crash.count' : 'app.error.count',
      attributes: {
        'error.type': (errorDetails.metadata['error_type'] as String?) ?? 'unknown',
        'screen.name': _currentScreen,
      },
    );

    if (isCrash) {
      _forceFlushAll();
    }
  }

  Future<void> _forceFlushAll() async {
    try {
      await Future.wait([
        TelemetryService.instance.flush(),
        MetricsService.instance.flush(),
        LogService.instance.flush(),
      ]).timeout(const Duration(seconds: 3));
    } catch (_) {
      // Best effort — don't let flush failure mask the crash
    }
  }

  void reportSessionEnd() {
    MetricsService.instance.incrementCounter(
      'app.session.count',
      attributes: {'crash_free': (!_hasCrashed).toString()},
    );
  }

  List<ErrorDetails> getRecentErrors({int? limit}) {
    if (limit != null && limit < _recentErrors.length) {
      return _recentErrors.take(limit).toList();
    }
    return List.unmodifiable(_recentErrors);
  }

  Map<String, dynamic> getErrorSummary() {
    if (_recentErrors.isEmpty) {
      return {
        'total_errors': 0,
        'error_types': <String, int>{},
        'last_error': null,
      };
    }

    final errorTypes = <String, int>{};
    for (final error in _recentErrors) {
      final type = error.metadata['error_type'] as String? ?? 'unknown';
      errorTypes[type] = (errorTypes[type] ?? 0) + 1;
    }

    return {
      'total_errors': _recentErrors.length,
      'error_types': errorTypes,
      'last_error': _recentErrors.first.toJson(),
      'session_start': TelemetryService.instance.sessionStartTime.toIso8601String(),
    };
  }

  void clearErrors() {
    final errorCount = _recentErrors.length;
    _recentErrors.clear();

    TelemetryService.instance.recordEvent('errors_cleared', attributes: {
      'cleared_count': errorCount,
      'session_id': TelemetryService.instance.sessionId,
    });
  }

  bool get hasRecentErrors => _recentErrors.isNotEmpty;

  int get errorCount => _recentErrors.length;

  String? get lastErrorMessage =>
    _recentErrors.isNotEmpty ? _recentErrors.first.error : null;
}
