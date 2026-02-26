import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';
import 'package:http/http.dart' as http;
import 'package:opentelemetry/api.dart' as otel;
import 'package:uuid/uuid.dart';

class TelemetryService {
  TelemetryService._internal();

  static TelemetryService? _instance;
  static String? _accessToken;
  static DateTime? _tokenExpiry;

  static String get otlpEndpoint {
    final endpoint = dotenv.env['OTLP_ENDPOINT'];
    if (endpoint == null || endpoint.isEmpty) {
      throw Exception('OTLP_ENDPOINT environment variable is required');
    }
    return endpoint;
  }
  
  static String get otlpTracesExporter {
    final exporter = dotenv.env['OTLP_TRACES_EXPORTER'];
    if (exporter == null || exporter.isEmpty) {
      throw Exception('OTLP_TRACES_EXPORTER environment variable is required');
    }
    return exporter;
  }
  
  static String get otlpMetricsExporter {
    final exporter = dotenv.env['OTLP_METRICS_EXPORTER'];
    if (exporter == null || exporter.isEmpty) {
      throw Exception('OTLP_METRICS_EXPORTER environment variable is required');
    }
    return exporter;
  }
  
  static String get otlpLogsExporter {
    final exporter = dotenv.env['OTLP_LOGS_EXPORTER'];
    if (exporter == null || exporter.isEmpty) {
      throw Exception('OTLP_LOGS_EXPORTER environment variable is required');
    }
    return exporter;
  }
  
  static String get otlpTracesEndpoint => '$otlpEndpoint/$otlpTracesExporter';
  
  
  static String get serviceName => dotenv.env['SERVICE_NAME'] ?? 'astronomy-shop-mobile';
  static String get serviceVersion => dotenv.env['SERVICE_VERSION'] ?? '1.0.0';
  static String get environment => dotenv.env['ENVIRONMENT'] ?? 'development';

  // Scout/OIDC Authentication Configuration
  static String? get scoutClientId => dotenv.env['SCOUT_CLIENT_ID'];
  static String? get scoutClientSecret => dotenv.env['SCOUT_CLIENT_SECRET'];
  static String? get scoutTokenUrl => dotenv.env['SCOUT_TOKEN_URL'];
  static String? get scoutEndpoint => dotenv.env['SCOUT_ENDPOINT'];

  late final otel.Tracer _tracer;
  late final String _sessionId;
  late final DateTime _sessionStartTime;
  late final http.Client _httpClient;

  String? _currentTraceId; // Current operation trace ID
  String? _currentParentSpanId; // Current parent span for hierarchy
  final Map<String, String> _activeTraces = {}; // Track active traces by operation
  double _batteryLevel = 1.0;
  bool _isLowPowerMode = false;
  double _samplingRate = 1.0;
  final Random _random = Random.secure();

  static const _batteryChannel = MethodChannel('battery');

  static const double _lowBatteryThreshold = 0.20;
  static const double _criticalBatteryThreshold = 0.10;

  static const double _normalSamplingRate = 1.0;
  static const double _lowBatterySamplingRate = 0.5;
  static const double _criticalBatterySamplingRate = 0.2;
  static const double _lowPowerModeSamplingRate = 0.3;

  final List<Map<String, dynamic>> _eventBatch = [];
  static const int _maxBatchSize = 50;
  static const Duration _batchFlushInterval = Duration(seconds: 30);
  Timer? _batchTimer;
  bool _isFlushingBatch = false;

  static TelemetryService get instance {
    _instance ??= TelemetryService._internal();
    return _instance!;
  }

  Future<void> initialize() async {
    try {
      _sessionId = const Uuid().v4();
      _sessionStartTime = DateTime.now();
      _httpClient = http.Client();
      _tracer = otel.globalTracerProvider.getTracer(serviceName, version: serviceVersion);
      _currentTraceId = _generateTraceId(); // Create session-wide trace ID
      await _initializeBatteryMonitoring();
      await _initializeAuthentication();
      _startBatchTimer();

      final initSpan = _tracer.startSpan('app_initialization');
      initSpan.setAttributes([
        otel.Attribute.fromString('app.version', serviceVersion),
        otel.Attribute.fromString('session.id', _sessionId),
        otel.Attribute.fromString('debug_mode', kDebugMode.toString()),
        otel.Attribute.fromString('device.platform', _getPlatform()),
        otel.Attribute.fromString('service.name', serviceName),
        otel.Attribute.fromDouble('battery.level', _batteryLevel),
        otel.Attribute.fromString('battery.low_power_mode', _isLowPowerMode.toString()),
        otel.Attribute.fromDouble('telemetry.sampling_rate', _samplingRate),
      ]);
      initSpan.end();

    } catch (e) {
      // Ignore initialization errors
    }
  }

  String _getPlatform() {
    if (kIsWeb) return 'web';
    return Platform.operatingSystem;
  }

  otel.Tracer get tracer => _tracer;

  String get sessionId => _sessionId;

  DateTime get sessionStartTime => _sessionStartTime;


  // Start a new trace for a business operation
  String startTrace(String operationName) {
    final traceId = _generateTraceId();
    _activeTraces[operationName] = traceId;
    _currentTraceId = traceId;
    _currentParentSpanId = null; // Reset parent for new trace

    if (kDebugMode) {
      print('📍 Started trace: $operationName | TraceID: ${traceId.substring(0, 8)}...');
    }

    return traceId;
  }

  // End a trace for a business operation
  void endTrace(String operationName) {
    _activeTraces.remove(operationName);
  }

  // Get or create trace for an operation
  String getOrCreateTrace(String operationName) {
    return _activeTraces[operationName] ?? startTrace(operationName);
  }

  void recordEvent(String name, {Map<String, Object>? attributes, bool immediate = false, String? parentOperation}) {
    if (!_shouldSample()) return;

    // Determine trace context
    String? traceId;
    String? parentSpanId;

    if (parentOperation != null) {
      traceId = getOrCreateTrace(parentOperation);
      parentSpanId = _currentParentSpanId;
    } else {
      // Create a new trace for standalone events
      traceId = _currentTraceId ?? startTrace('session_events');
    }

    final eventData = {
      'name': name,
      'timestamp': DateTime.now().millisecondsSinceEpoch,
      'battery_level': _batteryLevel,
      'sampling_rate': _samplingRate,
      'session_id': _sessionId,
      'trace_id': traceId,
      'parent_span_id': parentSpanId,
      ...?attributes,
    };

    // Always send spans immediately to preserve hierarchy
    _createAndSendSpan(eventData);
  }

  void _createAndSendSpan(Map<String, dynamic> eventData) {
    final spanName = eventData['name']?.toString() ?? 'custom_event';
    final span = _tracer.startSpan(spanName);

    span.setAttributes(
      eventData.entries.where((entry) => entry.key != 'name').map((entry) {
        final value = entry.value;
        if (value is String) {
          return otel.Attribute.fromString(entry.key, value);
        } else if (value is int) {
          return otel.Attribute.fromInt(entry.key, value);
        } else if (value is double) {
          return otel.Attribute.fromDouble(entry.key, value);
        } else if (value is bool) {
          return otel.Attribute.fromString(entry.key, value.toString());
        } else {
          return otel.Attribute.fromString(entry.key, value.toString());
        }
      }).toList(),
    );

    span.end();

    // Send individual span directly to OTLP
    _sendIndividualSpanToOTLP(spanName, eventData);
  }


  void recordError(String operation, Object error, {StackTrace? stackTrace}) {
    final span = _tracer.startSpan('error_event');
    span.setAttributes([
      otel.Attribute.fromString('operation', operation),
      otel.Attribute.fromString('error.type', error.runtimeType.toString()),
      otel.Attribute.fromString('error.message', error.toString()),
      otel.Attribute.fromDouble('battery.level', _batteryLevel),
      otel.Attribute.fromDouble('telemetry.sampling_rate', _samplingRate),
    ]);

    if (stackTrace != null) {
      span.recordException(error, stackTrace: stackTrace);
    }

    span.setStatus(otel.StatusCode.error, error.toString());
    span.end();
  }

  Future<void> flush() async {
    try {
      await _flushBatch();
    } catch (e) {
      // Ignore initialization errors
    }
  }

  Future<void> shutdown() async {
    try {
      _batchTimer?.cancel();
      await _flushBatch();

      final shutdownSpan = _tracer.startSpan('app_shutdown');
      shutdownSpan.setAttributes([
        otel.Attribute.fromString('session.id', _sessionId),
        otel.Attribute.fromInt('timestamp', DateTime.now().millisecondsSinceEpoch),
        otel.Attribute.fromDouble('battery.level', _batteryLevel),
      ]);
      shutdownSpan.end();
    } catch (e) {
      // Ignore initialization errors
    }
  }

  Future<void> _initializeBatteryMonitoring() async {
    try {
      await _updateBatteryInfo();
    } catch (e) {
      _batteryLevel = 1.0;
      _isLowPowerMode = false;
    }

    _updateSamplingRate();
  }

  Future<void> _updateBatteryInfo() async {
    try {
      if (!kIsWeb && (Platform.isIOS || Platform.isAndroid)) {
        final batteryLevel = await _batteryChannel.invokeMethod<double>('getBatteryLevel') ?? 1.0;
        final lowPowerMode = await _batteryChannel.invokeMethod<bool>('isInLowPowerMode') ?? false;

        _batteryLevel = batteryLevel;
        _isLowPowerMode = lowPowerMode;
      }
    } catch (e) {
      _batteryLevel = 1.0;
      _isLowPowerMode = false;
    }
  }

  void _updateSamplingRate() {
    if (_isLowPowerMode) {
      _samplingRate = _lowPowerModeSamplingRate;
    } else if (_batteryLevel <= _criticalBatteryThreshold) {
      _samplingRate = _criticalBatterySamplingRate;
    } else if (_batteryLevel <= _lowBatteryThreshold) {
      _samplingRate = _lowBatterySamplingRate;
    } else {
      _samplingRate = _normalSamplingRate;
    }
  }

  bool _shouldSample() {
    if (_samplingRate >= 1.0) return true;
    if (_samplingRate <= 0.0) return false;

    return _random.nextDouble() < _samplingRate;
  }

  Future<void> updateBatteryStatus() async {
    await _updateBatteryInfo();
    final oldSamplingRate = _samplingRate;
    _updateSamplingRate();

    if (oldSamplingRate != _samplingRate) {
      recordEvent('telemetry_sampling_rate_changed', attributes: {
        'old_sampling_rate': oldSamplingRate,
        'new_sampling_rate': _samplingRate,
        'battery_level': _batteryLevel,
        'low_power_mode': _isLowPowerMode,
      });
    }
  }

  Future<void> _initializeAuthentication() async {
    if (scoutClientId != null && scoutClientSecret != null && scoutTokenUrl != null) {
      await _fetchAccessToken();
    }
  }

  Future<void> _fetchAccessToken() async {
    try {
      if (scoutClientId == null || scoutClientSecret == null || scoutTokenUrl == null) {
        return;
      }

      final credentials = base64Encode(utf8.encode('$scoutClientId:$scoutClientSecret'));

      final response = await _httpClient.post(
        Uri.parse(scoutTokenUrl!),
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          'Authorization': 'Basic $credentials',
        },
        body: 'grant_type=client_credentials',
      );

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        _accessToken = data['access_token'] as String?;

        // Calculate token expiry (use expires_in if provided, default to 1 hour)
        final expiresIn = data['expires_in'] as int? ?? 3600;
        _tokenExpiry = DateTime.now().add(Duration(seconds: expiresIn - 60)); // Refresh 1 minute early

        if (kDebugMode) {
          // Only show token validity duration, not exact expiry time
          final validityMinutes = expiresIn ~/ 60;
          print('🔐 Scout authentication successful, token valid for $validityMinutes minutes');
        }
      } else {
        if (kDebugMode) {
          print('❌ Scout authentication failed: ${response.statusCode}');
        }
      }
    } catch (e) {
      if (kDebugMode) {
        print('❌ Error fetching Scout access token: $e');
      }
    }
  }

  Future<void> _ensureValidToken() async {
    if (_accessToken == null ||
        _tokenExpiry == null ||
        DateTime.now().isAfter(_tokenExpiry!)) {
      await _fetchAccessToken();
    }
  }

  Map<String, dynamic> getBatteryInfo() {
    return {
      'battery_level': _batteryLevel,
      'is_low_power_mode': _isLowPowerMode,
      'sampling_rate': _samplingRate,
      'low_battery_threshold': _lowBatteryThreshold,
      'critical_battery_threshold': _criticalBatteryThreshold,
    };
  }

  void _startBatchTimer() {
    _batchTimer?.cancel();
    _batchTimer = Timer.periodic(_batchFlushInterval, (timer) {
      _flushBatch();
    });
  }

  Future<void> _flushBatch() async {
    if (_isFlushingBatch || _eventBatch.isEmpty) return;

    _isFlushingBatch = true;

    try {
      final batchToFlush = List<Map<String, dynamic>>.from(_eventBatch);
      _eventBatch.clear();

      final batchSpan = _tracer.startSpan('telemetry_batch');
      batchSpan.setAttributes([
        otel.Attribute.fromInt('batch.size', batchToFlush.length),
        otel.Attribute.fromString('session.id', _sessionId),
        otel.Attribute.fromInt('batch.timestamp', DateTime.now().millisecondsSinceEpoch),
        otel.Attribute.fromDouble('battery.level', _batteryLevel),
      ]);

      for (final eventData in batchToFlush) {
        final eventName = eventData['name']?.toString() ?? 'unknown_event';
        batchSpan.addEvent(eventName, attributes: eventData.entries
          .where((entry) => entry.key != 'name')
          .map((entry) {
            final value = entry.value;
            if (value is String) {
              return otel.Attribute.fromString(entry.key, value);
            } else if (value is int) {
              return otel.Attribute.fromInt(entry.key, value);
            } else if (value is double) {
              return otel.Attribute.fromDouble(entry.key, value);
            } else if (value is bool) {
              return otel.Attribute.fromString(entry.key, value.toString());
            } else {
              return otel.Attribute.fromString(entry.key, value.toString());
            }
          }).toList());
      }

      batchSpan.setStatus(otel.StatusCode.ok);
      batchSpan.end();

      await _sendToOTLPCollector(batchToFlush);

    } catch (e) {
      recordEvent('telemetry_batch_error', attributes: {
        'error': e.toString(),
        'batch_size': _eventBatch.length,
      }, immediate: true);
    } finally {
      _isFlushingBatch = false;
    }
  }

  Map<String, dynamic> getBatchInfo() {
    return {
      'current_batch_size': _eventBatch.length,
      'max_batch_size': _maxBatchSize,
      'batch_flush_interval_seconds': _batchFlushInterval.inSeconds,
      'is_flushing': _isFlushingBatch,
      'timer_active': _batchTimer?.isActive ?? false,
    };
  }

  void forceBatchFlush() {
    _flushBatch();
  }

  Future<void> _sendToOTLPCollector(List<Map<String, dynamic>> events) async {

    try {
      final traceId = _generateTraceId();
      final spanId = _generateSpanId();
      final now = DateTime.now();
      final startTime = now.microsecondsSinceEpoch * 1000;
      final endTime = (now.microsecondsSinceEpoch + 1000) * 1000;

      final spanEvents = events.map((event) {
        return {
          'timeUnixNano': (event['timestamp'] as int? ?? now.millisecondsSinceEpoch) * 1000000,
          'name': event['name'] ?? 'mobile_event',
          'attributes': _convertAttributesToOTLP(event),
        };
      }).toList();

      final otlpPayload = {
        'resourceSpans': [
          {
            'resource': {
              'attributes': _getResourceAttributes(),
            },
            'scopeSpans': [
              {
                'scope': {
                  'name': serviceName,
                  'version': serviceVersion,
                },
                'spans': [
                  {
                    'traceId': traceId,
                    'spanId': spanId,
                    'name': 'mobile_telemetry_batch',
                    'kind': 1,
                    'startTimeUnixNano': startTime,
                    'endTimeUnixNano': endTime,
                    'attributes': [
                      {'key': 'batch.size', 'value': {'intValue': events.length}},
                      {'key': 'battery.level', 'value': {'doubleValue': _batteryLevel}},
                      {'key': 'sampling.rate', 'value': {'doubleValue': _samplingRate}},
                      {'key': 'platform', 'value': {'stringValue': _getPlatform()}},
                    ],
                    'events': spanEvents,
                    'status': {'code': 1},
                  }
                ],
              }
            ],
          }
        ],
      };

      // Ensure we have a valid token if using Scout endpoint
      await _ensureValidToken();

      final headers = <String, String>{
        'Content-Type': 'application/json',
        'User-Agent': '$serviceName/$serviceVersion',
      };

      // Add Bearer token if available
      if (_accessToken != null) {
        headers['Authorization'] = 'Bearer $_accessToken';
      }

      // Use Scout endpoint if configured, otherwise use regular OTLP endpoint
      final endpoint = scoutEndpoint != null && _accessToken != null
          ? '$scoutEndpoint/$otlpTracesExporter'
          : otlpTracesEndpoint;

      final response = await _httpClient.post(
        Uri.parse(endpoint),
        headers: headers,
        body: jsonEncode(otlpPayload),
      );

      if (kDebugMode) {
        if (response.statusCode == 200) {
          print('✅ OTLP batch sent: ${events.length} events');
        } else {
          print('❌ OTLP batch failed: ${response.statusCode}');
        }
      }


    } catch (e) {
      // Ignore telemetry export errors
    }
  }

  List<Map<String, dynamic>> _convertAttributesToOTLP(Map<String, dynamic> attributes) {
    return attributes.entries
        .where((entry) => entry.key != 'name' && entry.key != 'timestamp')
        .map((entry) {
      final value = entry.value;
      Map<String, dynamic> otlpValue;

      if (value is String) {
        otlpValue = {'stringValue': value};
      } else if (value is int) {
        otlpValue = {'intValue': value};
      } else if (value is double) {
        otlpValue = {'doubleValue': value};
      } else if (value is bool) {
        otlpValue = {'boolValue': value};
      } else {
        otlpValue = {'stringValue': value.toString()};
      }

      return {
        'key': entry.key,
        'value': otlpValue,
      };
    }).toList();
  }

  List<Map<String, dynamic>> _getResourceAttributes() {
    return [
      {'key': 'service.name', 'value': {'stringValue': serviceName}},
      {'key': 'service.version', 'value': {'stringValue': serviceVersion}},
      {'key': 'deployment.environment', 'value': {'stringValue': environment}},
      {'key': 'telemetry.sdk.name', 'value': {'stringValue': 'flutter-opentelemetry'}},
      {'key': 'telemetry.sdk.version', 'value': {'stringValue': '0.18.10'}},
      {'key': 'session.id', 'value': {'stringValue': _sessionId}},
    ];
  }

  String _generateTraceId() {
    final bytes = List.generate(16, (i) => _random.nextInt(256));
    return bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join('');
  }

  String _generateSpanId() {
    final bytes = List.generate(8, (i) => _random.nextInt(256));
    return bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join('');
  }

  Future<void> _sendIndividualSpanToOTLP(String spanName, Map<String, dynamic> eventData) async {
    try {
      final traceId = eventData['trace_id']?.toString() ?? _generateTraceId();
      final spanId = _generateSpanId();
      final parentSpanId = eventData['parent_span_id']?.toString();
      final now = DateTime.now();
      final startTime = now.microsecondsSinceEpoch * 1000;
      final endTime = (now.microsecondsSinceEpoch + 1000) * 1000;

      // Update current parent span for next child spans
      if (eventData['name'] == 'screen_view' || eventData['name']?.toString().contains('_start') == true) {
        _currentParentSpanId = spanId;
      }

      final otlpPayload = {
        'resourceSpans': [
          {
            'resource': {
              'attributes': _getResourceAttributes(),
            },
            'scopeSpans': [
              {
                'scope': {
                  'name': serviceName,
                  'version': serviceVersion,
                },
                'spans': [
                  {
                    'traceId': traceId,
                    'spanId': spanId,
                    if (parentSpanId != null) 'parentSpanId': parentSpanId,
                    'name': spanName,
                    'kind': 1, // SPAN_KIND_INTERNAL
                    'startTimeUnixNano': startTime,
                    'endTimeUnixNano': endTime,
                    'attributes': _convertAttributesToOTLP(eventData),
                    'status': {'code': 1}, // STATUS_CODE_OK
                  }
                ],
              }
            ],
          }
        ],
      };

      // Ensure we have a valid token if using Scout endpoint
      await _ensureValidToken();

      final headers = <String, String>{
        'Content-Type': 'application/json',
        'User-Agent': '$serviceName/$serviceVersion',
      };

      // Add Bearer token if available
      if (_accessToken != null) {
        headers['Authorization'] = 'Bearer $_accessToken';
      }

      // Use Scout endpoint if configured, otherwise use regular OTLP endpoint
      final endpoint = scoutEndpoint != null && _accessToken != null
          ? '$scoutEndpoint/$otlpTracesExporter'
          : otlpTracesEndpoint;

      final response = await _httpClient.post(
        Uri.parse(endpoint),
        headers: headers,
        body: jsonEncode(otlpPayload),
      );

      if (kDebugMode) {
        if (response.statusCode == 200) {
          print('✅ OTLP span sent: $spanName');
        } else {
          print('❌ OTLP span failed: $spanName (${response.statusCode})');
        }
      }


    } catch (e) {
      // Ignore individual span export errors
    }
  }
}