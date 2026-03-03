import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import '../services/telemetry_service.dart';

class ErrorBoundary extends StatefulWidget {
  const ErrorBoundary({
    super.key,
    required this.child,
    required this.context,
    this.onRetry,
  });

  final Widget child;
  final String context;
  final VoidCallback? onRetry;

  @override
  State<ErrorBoundary> createState() => _ErrorBoundaryState();
}

class _ErrorBoundaryState extends State<ErrorBoundary> {
  Object? _error;
  StackTrace? _stackTrace;

  @override
  void initState() {
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    if (_error != null) {
      return _buildErrorUI();
    }

    return ErrorHandler(
      onError: _handleError,
      child: widget.child,
    );
  }

  Widget _buildErrorUI() {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF1A1B4B)),
        useMaterial3: true,
      ),
      home: Scaffold(
        backgroundColor: Colors.white,
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const Icon(
                  Icons.error_outline,
                  size: 64,
                  color: Colors.red,
                ),
                const SizedBox(height: 16),
                const Text(
                  'Something went wrong',
                  style: TextStyle(
                    fontSize: 24,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  'An error occurred in ${widget.context}',
                  style: const TextStyle(
                    fontSize: 16,
                    color: Colors.grey,
                  ),
                ),
                const SizedBox(height: 24),
                Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    OutlinedButton(
                      onPressed: _showErrorDetails,
                      child: const Text('Details'),
                    ),
                    const SizedBox(width: 12),
                    ElevatedButton(
                      onPressed: widget.onRetry ?? _retryDefault,
                      child: const Text('Retry'),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  void _handleError(Object error, StackTrace stackTrace) {
    // UI recovery only — telemetry recording is handled by the chained
    // ErrorHandlerService._handleFlutterError via FlutterError.onError
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        setState(() {
          _error = error;
          _stackTrace = stackTrace;
        });
      }
    });

    debugPrint('Error in ${widget.context}: $error');
  }

  void _showErrorDetails() {
    // For now, just print the error details to console
    // In a real app, you might want to show them differently
    debugPrint('=== Error Details ===');
    debugPrint('Context: ${widget.context}');
    debugPrint('Error: ${_error.toString()}');
    if (_stackTrace != null) {
      debugPrint('Stack Trace: ${_stackTrace.toString()}');
    }
    debugPrint('==================');
  }


  void _retryDefault() {
    setState(() {
      _error = null;
      _stackTrace = null;
    });
    
    TelemetryService.instance.recordEvent('error_boundary_retry', attributes: {
      'context': widget.context,
    });
  }
}

class ErrorHandler extends StatefulWidget {
  const ErrorHandler({
    super.key,
    required this.child,
    required this.onError,
  });

  final Widget child;
  final void Function(Object error, StackTrace stackTrace) onError;

  @override
  State<ErrorHandler> createState() => _ErrorHandlerState();
}

class _ErrorHandlerState extends State<ErrorHandler> {
  void Function(FlutterErrorDetails)? _previousHandler;

  @override
  void initState() {
    super.initState();
    _previousHandler = FlutterError.onError;
    FlutterError.onError = _onFlutterError;
  }

  @override
  void dispose() {
    if (FlutterError.onError == _onFlutterError) {
      FlutterError.onError = _previousHandler;
    }
    super.dispose();
  }

  void _onFlutterError(FlutterErrorDetails details) {
    SchedulerBinding.instance.addPostFrameCallback((_) {
      widget.onError(details.exception, details.stack ?? StackTrace.current);
    });
    // Chain to the previous handler (ErrorHandlerService) for crash classification
    _previousHandler?.call(details);
  }

  @override
  Widget build(BuildContext context) {
    return widget.child;
  }
}

class AppErrorBoundary extends StatelessWidget {
  const AppErrorBoundary({
    super.key,
    required this.child,
  });

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return ErrorBoundary(
      context: 'app_root',
      child: child,
      onRetry: () {
        // Could restart the app or navigate to home
      },
    );
  }
}

// Extension for easy error boundary wrapping
extension WidgetErrorBoundary on Widget {
  Widget withErrorBoundary(String context, {VoidCallback? onRetry}) {
    return ErrorBoundary(
      context: context,
      onRetry: onRetry,
      child: this,
    );
  }
}