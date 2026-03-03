import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import 'telemetry_service.dart';

class HistogramBucket {
  HistogramBucket() : bucketCounts = List.filled(defaultBounds.length + 1, 0);

  double sum = 0;
  int totalCount = 0;
  final List<int> bucketCounts;

  static const List<double> defaultBounds = [
    5, 10, 25, 50, 75, 100, 250, 500, 1000, 2500, 5000, 10000,
  ];

  void record(num value) {
    final v = value.toDouble();
    sum += v;
    totalCount++;
    for (var i = 0; i < defaultBounds.length; i++) {
      if (v <= defaultBounds[i]) {
        bucketCounts[i]++;
        return;
      }
    }
    bucketCounts[defaultBounds.length]++;
  }
}

class _HistogramSnapshot {
  _HistogramSnapshot({
    required this.totalCount,
    required this.sum,
    required this.bucketCounts,
  });

  final int totalCount;
  final double sum;
  final List<int> bucketCounts;
}

class MetricsService {
  MetricsService._();

  static MetricsService? _instance;
  static MetricsService get instance => _instance ??= MetricsService._();

  final Map<String, Map<String, int>> _counters = {};
  final Map<String, Map<String, HistogramBucket>> _histograms = {};
  final Map<String, Map<String, double>> _gauges = {};

  Timer? _flushTimer;
  bool _isFlushing = false;
  late final http.Client _httpClient;

  static const Duration _flushInterval = Duration(seconds: 60);

  void initialize() {
    _httpClient = http.Client();
    _startFlushTimer();

    if (kDebugMode) {
      print('MetricsService initialized');
    }
  }

  void incrementCounter(String name, {Map<String, String> attributes = const {}}) {
    final key = _attributeKey(attributes);
    _counters.putIfAbsent(name, () => {});
    _counters[name]![key] = (_counters[name]![key] ?? 0) + 1;
  }

  void recordHistogram(String name, num value, {Map<String, String> attributes = const {}}) {
    final key = _attributeKey(attributes);
    _histograms.putIfAbsent(name, () => {});
    _histograms[name]!.putIfAbsent(key, HistogramBucket.new);
    _histograms[name]![key]!.record(value);
  }

  void setGauge(String name, double value, {Map<String, String> attributes = const {}}) {
    final key = _attributeKey(attributes);
    _gauges.putIfAbsent(name, () => {});
    _gauges[name]![key] = value;
  }

  String _attributeKey(Map<String, String> attributes) {
    if (attributes.isEmpty) return '';
    final sorted = attributes.entries.toList()..sort((a, b) => a.key.compareTo(b.key));
    return sorted.map((e) => '${e.key}=${e.value}').join('|');
  }

  Map<String, String> _parseAttributeKey(String key) {
    if (key.isEmpty) return {};
    final result = <String, String>{};
    for (final pair in key.split('|')) {
      final eqIndex = pair.indexOf('=');
      if (eqIndex > 0) {
        result[pair.substring(0, eqIndex)] = pair.substring(eqIndex + 1);
      }
    }
    return result;
  }

  void _startFlushTimer() {
    _flushTimer?.cancel();
    _flushTimer = Timer.periodic(_flushInterval, _onFlushTimer);
  }

  void _onFlushTimer(Timer _) {
    flush();
  }

  Future<void> flush() async {
    if (_isFlushing) return;
    if (_counters.isEmpty && _histograms.isEmpty && _gauges.isEmpty) return;

    _isFlushing = true;

    try {
      final countersSnapshot = Map<String, Map<String, int>>.from(
        _counters.map((k, v) => MapEntry(k, Map<String, int>.from(v))),
      );
      final histogramsSnapshot = _snapshotHistograms();
      final gaugesSnapshot = Map<String, Map<String, double>>.from(
        _gauges.map((k, v) => MapEntry(k, Map<String, double>.from(v))),
      );

      _counters.clear();
      _histograms.clear();
      _gauges.clear();

      await _sendMetrics(countersSnapshot, histogramsSnapshot, gaugesSnapshot);
    } catch (e) {
      if (kDebugMode) {
        print('MetricsService flush error: $e');
      }
    } finally {
      _isFlushing = false;
    }
  }

  Map<String, Map<String, _HistogramSnapshot>> _snapshotHistograms() {
    final snapshot = <String, Map<String, _HistogramSnapshot>>{};
    for (final entry in _histograms.entries) {
      final inner = <String, _HistogramSnapshot>{};
      for (final attrEntry in entry.value.entries) {
        final bucket = attrEntry.value;
        inner[attrEntry.key] = _HistogramSnapshot(
          totalCount: bucket.totalCount,
          sum: bucket.sum,
          bucketCounts: List<int>.from(bucket.bucketCounts),
        );
      }
      snapshot[entry.key] = inner;
    }
    return snapshot;
  }

  Future<void> _sendMetrics(
    Map<String, Map<String, int>> counters,
    Map<String, Map<String, _HistogramSnapshot>> histograms,
    Map<String, Map<String, double>> gauges,
  ) async {
    final now = DateTime.now();
    final timeNano = now.microsecondsSinceEpoch * 1000;
    final metrics = <Map<String, dynamic>>[];

    for (final entry in counters.entries) {
      final dataPoints = <Map<String, dynamic>>[];
      for (final attrEntry in entry.value.entries) {
        dataPoints.add({
          'attributes': _otlpAttributes(_parseAttributeKey(attrEntry.key)),
          'startTimeUnixNano': timeNano,
          'timeUnixNano': timeNano,
          'asInt': attrEntry.value,
        });
      }
      metrics.add({
        'name': entry.key,
        'sum': {
          'dataPoints': dataPoints,
          'aggregationTemporality': 2,
          'isMonotonic': true,
        },
      });
    }

    for (final entry in histograms.entries) {
      final dataPoints = <Map<String, dynamic>>[];
      for (final attrEntry in entry.value.entries) {
        final snap = attrEntry.value;
        dataPoints.add({
          'attributes': _otlpAttributes(_parseAttributeKey(attrEntry.key)),
          'startTimeUnixNano': timeNano,
          'timeUnixNano': timeNano,
          'count': snap.totalCount,
          'sum': snap.sum,
          'explicitBounds': HistogramBucket.defaultBounds,
          'bucketCounts': snap.bucketCounts,
        });
      }
      metrics.add({
        'name': entry.key,
        'histogram': {
          'dataPoints': dataPoints,
          'aggregationTemporality': 2,
        },
      });
    }

    for (final entry in gauges.entries) {
      final dataPoints = <Map<String, dynamic>>[];
      for (final attrEntry in entry.value.entries) {
        dataPoints.add({
          'attributes': _otlpAttributes(_parseAttributeKey(attrEntry.key)),
          'timeUnixNano': timeNano,
          'asDouble': attrEntry.value,
        });
      }
      metrics.add({
        'name': entry.key,
        'gauge': {
          'dataPoints': dataPoints,
        },
      });
    }

    if (metrics.isEmpty) return;

    final payload = {
      'resourceMetrics': [
        {
          'resource': {
            'attributes': TelemetryService.instance.getResourceAttributes(),
          },
          'scopeMetrics': [
            {
              'scope': {
                'name': TelemetryService.serviceName,
                'version': TelemetryService.serviceVersion,
              },
              'metrics': metrics,
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
          print('OTLP metrics sent: ${metrics.length} metrics');
        } else {
          print('OTLP metrics failed: ${response.statusCode}');
        }
      }
    } catch (e) {
      if (kDebugMode) {
        print('OTLP metrics export error: $e');
      }
    }
  }

  String _buildEndpoint() {
    final scoutEndpoint = TelemetryService.scoutEndpoint;
    final token = TelemetryService.instance.accessToken;
    if (scoutEndpoint != null && token != null) {
      return '$scoutEndpoint/${TelemetryService.otlpMetricsExporter}';
    }
    return '${TelemetryService.otlpEndpoint}/${TelemetryService.otlpMetricsExporter}';
  }

  List<Map<String, dynamic>> _otlpAttributes(Map<String, String> attributes) {
    return attributes.entries.map((e) => {
      'key': e.key,
      'value': {'stringValue': e.value},
    }).toList();
  }

  void shutdown() {
    _flushTimer?.cancel();
    _httpClient.close();
  }
}
