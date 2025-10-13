import 'package:flutter/services.dart';
import 'telemetry_service.dart';

class PerformanceMetrics {
  final String operationName;
  final DateTime startTime;
  final Duration duration;
  final Map<String, dynamic> metadata;
  
  const PerformanceMetrics({
    required this.operationName,
    required this.startTime,
    required this.duration,
    this.metadata = const {},
  });
  
  double get durationMs => duration.inMicroseconds / 1000.0;
}

class PerformanceService {
  static PerformanceService? _instance;
  static PerformanceService get instance => _instance ??= PerformanceService._();
  
  PerformanceService._();
  
  final Map<String, DateTime> _operationStarts = {};
  final List<PerformanceMetrics> _metrics = [];
  
  void initialize() {
    TelemetryService.instance.recordEvent('performance_service_initialize', attributes: {
      'session_id': TelemetryService.instance.sessionId,
    });
  }
  
  void startOperation(String operationName, {Map<String, dynamic>? metadata}) {
    _operationStarts[operationName] = DateTime.now();
  }
  
  void endOperation(String operationName, {Map<String, dynamic>? metadata}) {
    final startTime = _operationStarts.remove(operationName);
    if (startTime == null) {
      return;
    }
    
    final endTime = DateTime.now();
    final duration = endTime.difference(startTime);
    
    final metrics = PerformanceMetrics(
      operationName: operationName,
      startTime: startTime,
      duration: duration,
      metadata: metadata ?? {},
    );
    
    _metrics.add(metrics);
    
    TelemetryService.instance.recordEvent('performance_metric', attributes: {
      'operation_name': operationName,
      'duration_ms': metrics.durationMs,
      'session_id': TelemetryService.instance.sessionId,
      ...?metadata,
    });
    
    if (metrics.durationMs > 1000) {
      _recordSlowOperation(metrics);
    }
  }
  
  void recordMemoryUsage() {
    SystemChannels.platform.invokeMethod('SystemNavigator.routeUpdated').catchError((_) {});
    
    final estimatedMemoryMB = _metrics.length * 0.1;
    
    TelemetryService.instance.recordEvent('memory_usage', attributes: {
      'estimated_memory_mb': estimatedMemoryMB,
      'metrics_count': _metrics.length,
      'session_id': TelemetryService.instance.sessionId,
    });
  }
  
  void recordFrameMetrics({
    required double averageFPS,
    required int droppedFrames,
    required String screenName,
  }) {
    TelemetryService.instance.recordEvent('frame_metrics', attributes: {
      'average_fps': averageFPS,
      'dropped_frames': droppedFrames,
      'screen_name': screenName,
      'session_id': TelemetryService.instance.sessionId,
    });
  }
  
  void _recordSlowOperation(PerformanceMetrics metrics) {
    TelemetryService.instance.recordEvent('slow_operation_detected', attributes: {
      'operation_name': metrics.operationName,
      'duration_ms': metrics.durationMs,
      'severity': metrics.durationMs > 5000 ? 'critical' : 'warning',
      'session_id': TelemetryService.instance.sessionId,
    });
  }
  
  List<PerformanceMetrics> getMetrics({String? operationName}) {
    if (operationName != null) {
      return _metrics.where((m) => m.operationName == operationName).toList();
    }
    return List.unmodifiable(_metrics);
  }
  
  Map<String, dynamic> getPerformanceSummary() {
    final summary = <String, dynamic>{
      'total_operations': _metrics.length,
      'session_duration_ms': DateTime.now().difference(
        TelemetryService.instance.sessionStartTime
      ).inMilliseconds,
    };
    
    if (_metrics.isNotEmpty) {
      final durations = _metrics.map((m) => m.durationMs).toList();
      durations.sort();
      
      summary.addAll({
        'average_duration_ms': durations.fold(0.0, (a, b) => a + b) / durations.length,
        'median_duration_ms': durations[durations.length ~/ 2],
        'p95_duration_ms': durations[(durations.length * 0.95).floor()],
        'slowest_operation': _metrics.reduce((a, b) => 
          a.durationMs > b.durationMs ? a : b).operationName,
      });
    }
    
    return summary;
  }
  
  void clearMetrics() {
    _metrics.clear();
    _operationStarts.clear();
  }
}