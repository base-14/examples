// Copyright 2020 The Flutter team. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:battery_plus/battery_plus.dart';
import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:device_info_plus/device_info_plus.dart';
import 'package:flutterrific_opentelemetry/flutterrific_opentelemetry.dart';
import 'package:package_info_plus/package_info_plus.dart';

/// Central RUM state singleton — holds session, user, device, screen,
/// network, battery, and breadcrumb context. [getCommonAttributes] returns
/// a fresh snapshot called by [RumSpanProcessor] on every span.
///
/// Attribute names follow OTel semantic conventions:
/// - https://opentelemetry.io/docs/specs/semconv/general/session/
/// - https://opentelemetry.io/docs/specs/semconv/resource/device/
/// - https://opentelemetry.io/docs/specs/semconv/registry/attributes/app/
class RumSession {
  RumSession._();
  static final RumSession instance = RumSession._();

  // --- Session (semconv: session.*) ---
  String sessionId = 'pending';
  DateTime sessionStart = DateTime.now();

  // --- User ---
  String? _userId;
  String? _userEmail;
  String? _userRole;

  // --- Current Screen (semconv: app.screen.*) ---
  String _currentScreen = '/';
  DateTime _screenEnteredAt = DateTime.now();

  // --- Device (semconv: device.*) ---
  String _deviceModelIdentifier = 'unknown';
  String _deviceModelName = 'unknown';
  String _deviceManufacturer = 'unknown';
  String _deviceId = 'unknown';

  // --- App (semconv: app.*, service.*) ---
  String _appVersion = 'unknown';
  String _appBuildId = 'unknown';
  String _appPackageName = 'unknown';
  String _appInstallationId = 'unknown';

  // --- Network ---
  String _networkType = 'unknown';
  StreamSubscription<List<ConnectivityResult>>? _connectivitySub;

  // --- Cold Start ---
  Duration? coldStartDuration;

  // --- Breadcrumbs ---
  static const int _maxBreadcrumbs = 20;
  final List<Map<String, String>> _breadcrumbs = [];

  // --- Battery ---
  final Battery _battery = Battery();
  int _batteryLevel = 100;
  String _batteryState = 'unknown';
  StreamSubscription<BatteryState>? _batterySub;
  bool _forceSample = false;
  final Random _random = Random();

  Future<void> initialize() async {
    sessionId = DateTime.now().microsecondsSinceEpoch.toRadixString(36);
    sessionStart = DateTime.now();

    await _loadDeviceInfo();
    await _loadPackageInfo();
    await _initConnectivity();
    await _initBattery();
  }

  // --- User identification API ---

  void setUser({String? id, String? email, String? role}) {
    _userId = id;
    _userEmail = email;
    _userRole = role;
  }

  void clearUser() {
    _userId = null;
    _userEmail = null;
    _userRole = null;
  }

  // --- Screen tracking ---

  void setCurrentScreen(String screen) {
    _currentScreen = screen;
    _screenEnteredAt = DateTime.now();
  }

  String get currentScreen => _currentScreen;

  Duration get currentScreenDwellTime =>
      DateTime.now().difference(_screenEnteredAt);

  // --- Breadcrumb API ---

  /// Records a breadcrumb. Keeps the last [_maxBreadcrumbs] entries (FIFO).
  void recordBreadcrumb(String type, String label,
      [Map<String, String>? data]) {
    final crumb = <String, String>{
      'ts': DateTime.now().toIso8601String(),
      'type': type,
      'label': label,
    };
    if (data != null) crumb.addAll(data);

    _breadcrumbs.add(crumb);
    if (_breadcrumbs.length > _maxBreadcrumbs) {
      _breadcrumbs.removeAt(0);
    }
  }

  /// Returns JSON-encoded breadcrumb list for attaching to error spans.
  String getBreadcrumbString() => jsonEncode(_breadcrumbs);

  // --- Battery-aware sampling ---

  /// Returns true if this span should be sampled based on battery level.
  /// Error spans should call [forceNextSample] beforehand to guarantee capture.
  bool shouldSample() {
    if (_forceSample) {
      _forceSample = false;
      return true;
    }
    if (_batteryState == 'charging' || _batteryLevel > 20) {
      return true; // 100% sampling
    }
    if (_batteryLevel > 10) {
      return _random.nextDouble() < 0.5; // 50% sampling
    }
    return _random.nextDouble() < 0.2; // 20% sampling
  }

  /// Ensures the next call to [shouldSample] returns true.
  void forceNextSample() => _forceSample = true;

  /// Refreshes battery level on demand (e.g. when app resumes).
  Future<void> refreshBatteryState() async {
    _batteryLevel = await _battery.batteryLevel;
  }

  // --- Common attributes for every span (OTel semconv) ---

  Attributes getCommonAttributes() {
    final map = <String, Object>{
      // Session — semconv: session.*
      'session.id': sessionId,
      'session.start': sessionStart.toIso8601String(),
      'session.duration_ms':
          DateTime.now().difference(sessionStart).inMilliseconds,

      // Current screen — semconv: app.screen.*
      'app.screen.name': _currentScreen,

      // Device — semconv: device.*
      'device.model.identifier': _deviceModelIdentifier,
      'device.model.name': _deviceModelName,
      'device.manufacturer': _deviceManufacturer,
      'device.id': _deviceId,
      'os.type': Platform.operatingSystem,
      'os.version': Platform.operatingSystemVersion,

      // App — semconv: app.*, service.*
      'service.version': _appVersion,
      'app.build_id': _appBuildId,
      'app.installation.id': _appInstallationId,
      'service.name': _appPackageName,

      // Network
      'network.type': _networkType,

      // Battery
      'device.battery.level': _batteryLevel,
      'device.battery.state': _batteryState,
    };

    if (_userId != null) map['enduser.id'] = _userId!;
    if (_userEmail != null) map['enduser.email'] = _userEmail!;
    if (_userRole != null) map['enduser.role'] = _userRole!;

    if (coldStartDuration != null) {
      map['app.cold_start_ms'] = coldStartDuration!.inMilliseconds;
    }

    return map.toAttributes();
  }

  Future<void> _loadDeviceInfo() async {
    final deviceInfo = DeviceInfoPlugin();
    if (Platform.isAndroid) {
      final android = await deviceInfo.androidInfo;
      _deviceModelIdentifier = android.model;
      _deviceModelName = android.model;
      _deviceManufacturer = android.manufacturer;
      _deviceId = android.id;
      _appInstallationId = android.id;
    } else if (Platform.isIOS) {
      final ios = await deviceInfo.iosInfo;
      _deviceModelIdentifier = ios.utsname.machine;
      _deviceModelName = ios.name;
      _deviceManufacturer = 'Apple';
      _deviceId = ios.identifierForVendor ?? 'unknown';
      _appInstallationId = ios.identifierForVendor ?? 'unknown';
    }
  }

  Future<void> _loadPackageInfo() async {
    final info = await PackageInfo.fromPlatform();
    _appVersion = info.version;
    _appBuildId = info.buildNumber;
    _appPackageName = info.packageName;
  }

  Future<void> _initConnectivity() async {
    final connectivity = Connectivity();
    final results = await connectivity.checkConnectivity();
    _updateNetworkType(results);
    _connectivitySub =
        connectivity.onConnectivityChanged.listen(_updateNetworkType);
  }

  void _updateNetworkType(List<ConnectivityResult> results) {
    if (results.contains(ConnectivityResult.wifi)) {
      _networkType = 'wifi';
    } else if (results.contains(ConnectivityResult.mobile)) {
      _networkType = 'cellular';
    } else if (results.contains(ConnectivityResult.ethernet)) {
      _networkType = 'ethernet';
    } else if (results.contains(ConnectivityResult.none)) {
      _networkType = 'none';
    } else {
      _networkType = 'other';
    }
  }

  Future<void> _initBattery() async {
    try {
      _batteryLevel = await _battery.batteryLevel;
      final state = await _battery.batteryState;
      _updateBatteryState(state);
      _batterySub = _battery.onBatteryStateChanged.listen(_updateBatteryState);
    } catch (_) {
      // Battery info unavailable (e.g. emulator) — keep defaults.
    }
  }

  void _updateBatteryState(BatteryState state) {
    switch (state) {
      case BatteryState.charging:
        _batteryState = 'charging';
      case BatteryState.discharging:
        _batteryState = 'discharging';
      case BatteryState.full:
        _batteryState = 'full';
      case BatteryState.connectedNotCharging:
        _batteryState = 'connected_not_charging';
      case BatteryState.unknown:
        _batteryState = 'unknown';
    }
  }

  void dispose() {
    _connectivitySub?.cancel();
    _batterySub?.cancel();
  }
}
