import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import 'telemetry_service.dart';

enum LogSeverity {
  debug(5),
  info(9),
  warn(13),
  error(17),
  fatal(21);

  const LogSeverity(this.number);
  final int number;
}

class _LogRecord {
  _LogRecord({
    required this.message,
    required this.severity,
    required this.timeNano,
    this.attributes = const {},
    this.traceId,
    this.spanId,
    this.stackTrace,
  });

  final String message;
  final LogSeverity severity;
  final int timeNano;
  final Map<String, String> attributes;
  final String? traceId;
  final String? spanId;
  final String? stackTrace;
}

class LogService {
  LogService._();

  static LogService? _instance;
  static LogService get instance => _instance ??= LogService._();

  final List<_LogRecord> _buffer = [];
  static const int _maxBufferSize = 100;
  static const Duration _flushInterval = Duration(seconds: 30);
  static const int _maxStackTraceLength = 4000;

  Timer? _flushTimer;
  bool _isFlushing = false;
  late final http.Client _httpClient;

  void initialize() {
    _httpClient = http.Client();
    _startFlushTimer();

    if (kDebugMode) {
      print('LogService initialized');
    }
  }

  void debug(String message, {Map<String, String>? attributes}) {
    if (!TelemetryService.instance.shouldSampleForLogs()) return;
    _addRecord(message, LogSeverity.debug, attributes: attributes);
  }

  void info(String message, {Map<String, String>? attributes}) {
    if (!TelemetryService.instance.shouldSampleForLogs()) return;
    _addRecord(message, LogSeverity.info, attributes: attributes);
  }

  void warn(String message, {Map<String, String>? attributes, String? traceId, String? spanId}) {
    _addRecord(message, LogSeverity.warn, attributes: attributes, traceId: traceId, spanId: spanId);
  }

  void error(String message, {Object? exception, StackTrace? stackTrace, Map<String, String>? attributes, String? traceId, String? spanId}) {
    _addRecord(
      message,
      LogSeverity.error,
      attributes: attributes,
      traceId: traceId,
      spanId: spanId,
      stackTrace: _truncateStackTrace(stackTrace),
    );
  }

  void fatal(String message, {Object? exception, StackTrace? stackTrace, Map<String, String>? attributes}) {
    _addRecord(
      message,
      LogSeverity.fatal,
      attributes: attributes,
      stackTrace: _truncateStackTrace(stackTrace),
    );
    forceFlush();
  }

  String? _truncateStackTrace(StackTrace? stackTrace) {
    if (stackTrace == null) return null;
    final str = stackTrace.toString();
    if (str.length <= _maxStackTraceLength) return str;
    return '${str.substring(0, _maxStackTraceLength)}... [truncated]';
  }

  void _addRecord(String message, LogSeverity severity, {
    Map<String, String>? attributes,
    String? traceId,
    String? spanId,
    String? stackTrace,
  }) {
    final now = DateTime.now();
    _buffer.add(_LogRecord(
      message: message,
      severity: severity,
      timeNano: now.microsecondsSinceEpoch * 1000,
      attributes: attributes ?? {},
      traceId: traceId,
      spanId: spanId,
      stackTrace: stackTrace,
    ));

    if (_buffer.length >= _maxBufferSize) {
      flush();
    }
  }

  void _startFlushTimer() {
    _flushTimer?.cancel();
    _flushTimer = Timer.periodic(_flushInterval, (_) => flush());
  }

  void forceFlush() {
    flush();
  }

  Future<void> flush() async {
    if (_isFlushing || _buffer.isEmpty) return;

    _isFlushing = true;

    try {
      final records = List<_LogRecord>.from(_buffer);
      _buffer.clear();

      await _sendLogs(records);
    } catch (e) {
      if (kDebugMode) {
        print('LogService flush error: $e');
      }
    } finally {
      _isFlushing = false;
    }
  }

  Future<void> _sendLogs(List<_LogRecord> records) async {
    final logRecords = records.map((record) {
      final attrs = <Map<String, dynamic>>[
        ...record.attributes.entries.map((e) => {
          'key': e.key,
          'value': {'stringValue': e.value},
        }),
      ];

      if (record.stackTrace != null) {
        attrs.add({
          'key': 'exception.stacktrace',
          'value': {'stringValue': record.stackTrace!},
        });
      }

      return {
        'timeUnixNano': record.timeNano,
        'severityNumber': record.severity.number,
        'severityText': record.severity.name.toUpperCase(),
        'body': {'stringValue': record.message},
        'attributes': attrs,
        if (record.traceId != null) 'traceId': record.traceId,
        if (record.spanId != null) 'spanId': record.spanId,
      };
    }).toList();

    final payload = {
      'resourceLogs': [
        {
          'resource': {
            'attributes': TelemetryService.instance.getResourceAttributes(),
          },
          'scopeLogs': [
            {
              'scope': {
                'name': TelemetryService.serviceName,
                'version': TelemetryService.serviceVersion,
              },
              'logRecords': logRecords,
            },
          ],
        },
      ],
    };

    try {
      final endpoint = _buildEndpoint();
      final headers = <String, String>{
        'Content-Type': 'application/json',
        'User-Agent': '${TelemetryService.serviceName}/${TelemetryService.serviceVersion}',
      };

      final token = TelemetryService.instance.accessToken;
      if (token != null) {
        headers['Authorization'] = 'Bearer $token';
      }

      final response = await _httpClient.post(
        Uri.parse(endpoint),
        headers: headers,
        body: jsonEncode(payload),
      );

      if (kDebugMode) {
        if (response.statusCode == 200) {
          print('OTLP logs sent: ${logRecords.length} records');
        } else {
          print('OTLP logs failed: ${response.statusCode}');
        }
      }
    } catch (e) {
      if (kDebugMode) {
        print('OTLP logs export error: $e');
      }
    }
  }

  String _buildEndpoint() {
    final scoutEndpoint = TelemetryService.scoutEndpoint;
    final token = TelemetryService.instance.accessToken;
    if (scoutEndpoint != null && token != null) {
      return '$scoutEndpoint/${TelemetryService.otlpLogsExporter}';
    }
    return '${TelemetryService.otlpEndpoint}/${TelemetryService.otlpLogsExporter}';
  }

  void shutdown() {
    _flushTimer?.cancel();
    _httpClient.close();
  }
}
