import 'package:flutter/widgets.dart';
import 'package:opentelemetry/api.dart' as otel;

import 'performance_service.dart';
import 'telemetry_service.dart';

class AppLifecycleObserver extends WidgetsBindingObserver {
  AppLifecycleObserver() {
    _tracer = _telemetryService.tracer;
  }

  final TelemetryService _telemetryService = TelemetryService.instance;
  late final otel.Tracer _tracer;
  
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    super.didChangeAppLifecycleState(state);
    
    final span = _tracer.startSpan('app_lifecycle_change');
    span.setAttributes([
      otel.Attribute.fromString('lifecycle.state', state.name),
      otel.Attribute.fromString('session.id', _telemetryService.sessionId),
      otel.Attribute.fromInt('timestamp', DateTime.now().millisecondsSinceEpoch),
    ]);
    
    switch (state) {
      case AppLifecycleState.resumed:
        span.setAttributes([
          otel.Attribute.fromString('lifecycle.action', 'app_resumed'),
        ]);
        PerformanceService.instance.recordMemoryUsage();
        _telemetryService.updateBatteryStatus();
        
        break;
        
      case AppLifecycleState.paused:
        span.setAttributes([
          otel.Attribute.fromString('lifecycle.action', 'app_paused'),
        ]);
        // Flush telemetry when app goes to background
        _telemetryService.flush();
        
        break;
        
      case AppLifecycleState.detached:
        span.setAttributes([
          otel.Attribute.fromString('lifecycle.action', 'app_detached'),
        ]);
        // Final shutdown
        _telemetryService.shutdown();
        
        break;
        
      case AppLifecycleState.inactive:
        span.setAttributes([
          otel.Attribute.fromString('lifecycle.action', 'app_inactive'),
        ]);
        break;
        
      case AppLifecycleState.hidden:
        span.setAttributes([
          otel.Attribute.fromString('lifecycle.action', 'app_hidden'),
        ]);
        break;
    }
    
    span.end();
  }
}