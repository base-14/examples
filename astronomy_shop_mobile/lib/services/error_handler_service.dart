import 'package:flutter/foundation.dart';
import 'telemetry_service.dart';
import 'performance_service.dart';

class ErrorDetails {
  final String error;
  final String? stackTrace;
  final String? context;
  final DateTime timestamp;
  final Map<String, dynamic> metadata;
  
  const ErrorDetails({
    required this.error,
    this.stackTrace,
    this.context,
    required this.timestamp,
    this.metadata = const {},
  });
  
  Map<String, dynamic> toJson() => {
    'error': error,
    'stack_trace': stackTrace,
    'context': context,
    'timestamp': timestamp.toIso8601String(),
    'metadata': metadata,
  };
}

class ErrorHandlerService {
  static ErrorHandlerService? _instance;
  static ErrorHandlerService get instance => _instance ??= ErrorHandlerService._();
  
  ErrorHandlerService._();
  
  final List<ErrorDetails> _recentErrors = [];
  final int _maxRecentErrors = 50;
  
  void initialize() {
    FlutterError.onError = (FlutterErrorDetails details) {
      _handleFlutterError(details);
    };
    
    PlatformDispatcher.instance.onError = (error, stack) {
      _handlePlatformError(error, stack);
      return true;
    };
    
    TelemetryService.instance.recordEvent('error_handler_initialize', attributes: {
      'session_id': TelemetryService.instance.sessionId,
    });
  }
  
  void _handleFlutterError(FlutterErrorDetails details) {
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
    
    _recordError(errorDetails);
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
    
    _recordError(errorDetails);
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
  
  void _recordError(ErrorDetails errorDetails) {
    _recentErrors.insert(0, errorDetails);
    
    if (_recentErrors.length > _maxRecentErrors) {
      _recentErrors.removeLast();
    }
    
    TelemetryService.instance.recordEvent('error_occurred', attributes: {
      'error_message': errorDetails.error,
      'error_context': errorDetails.context ?? 'unknown',
      'error_type': errorDetails.metadata['error_type'] ?? 'unknown',
      'session_id': TelemetryService.instance.sessionId,
      'has_stack_trace': errorDetails.stackTrace != null,
      'error_timestamp': errorDetails.timestamp.millisecondsSinceEpoch,
    });
    
    PerformanceService.instance.endOperation('error_handling', metadata: {
      'error_type': errorDetails.metadata['error_type'],
      'error_handled': true,
    });
    
    if (kDebugMode) {
      if (errorDetails.stackTrace != null) {
      }
    }
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