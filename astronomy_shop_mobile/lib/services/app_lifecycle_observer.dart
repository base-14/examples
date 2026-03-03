import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';

import 'performance_service.dart';
import 'telemetry_service.dart';

class AppLifecycleObserver extends WidgetsBindingObserver {
  final TelemetryService _telemetryService = TelemetryService.instance;

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    super.didChangeAppLifecycleState(state);

    final stateKey = _platformStateKey();
    final stateValue = _mapLifecycleState(state);

    _telemetryService.recordEvent('device.app.lifecycle', attributes: {
      stateKey: stateValue,
      'session.id': _telemetryService.sessionId,
    });

    switch (state) {
      case AppLifecycleState.resumed:
        PerformanceService.instance.recordMemoryUsage();
        _telemetryService.updateBatteryStatus();
        break;

      case AppLifecycleState.paused:
        _telemetryService.flush();
        break;

      case AppLifecycleState.detached:
        _telemetryService.shutdown();
        break;

      case AppLifecycleState.inactive:
      case AppLifecycleState.hidden:
        break;
    }
  }

  String _platformStateKey() {
    if (kIsWeb) return 'android.app.state';
    if (Platform.isIOS) return 'ios.app.state';
    return 'android.app.state';
  }

  String _mapLifecycleState(AppLifecycleState state) {
    if (!kIsWeb && Platform.isIOS) {
      return switch (state) {
        AppLifecycleState.resumed => 'active',
        AppLifecycleState.inactive => 'inactive',
        AppLifecycleState.paused => 'background',
        AppLifecycleState.detached => 'terminate',
        AppLifecycleState.hidden => 'background',
      };
    }
    return switch (state) {
      AppLifecycleState.resumed => 'foreground',
      AppLifecycleState.inactive => 'created',
      AppLifecycleState.paused => 'background',
      AppLifecycleState.detached => 'background',
      AppLifecycleState.hidden => 'background',
    };
  }
}
