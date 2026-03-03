import 'dart:convert';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:opentelemetry/api.dart' as otel;

import 'config_service.dart';
import 'log_service.dart';
import 'metrics_service.dart';
import 'telemetry_service.dart';

class HttpService {
  HttpService._internal() {
    _tracer = TelemetryService.instance.tracer;
    _client = http.Client();
    _config = ConfigService.instance;
    _random = Random.secure();
  }

  static HttpService? _instance;

  late final otel.Tracer _tracer;
  late final http.Client _client;
  late final ConfigService _config;
  late final Random _random;

  static HttpService get instance {
    _instance ??= HttpService._internal();
    return _instance!;
  }

  String get baseUrl => _config.apiBaseUrl;

  Future<HttpResponse<T>> get<T>(
    String endpoint, {
    Map<String, String>? headers,
    Map<String, String>? queryParams,
    T Function(Map<String, dynamic>)? fromJson,
    List<T> Function(List<dynamic>)? fromJsonList,
  }) async {
    return _makeRequest<T>(
      'GET',
      endpoint,
      headers: headers,
      queryParams: queryParams,
      fromJson: fromJson,
      fromJsonList: fromJsonList,
    );
  }

  Future<HttpResponse<T>> post<T>(
    String endpoint, {
    Map<String, String>? headers,
    Object? body,
    T Function(Map<String, dynamic>)? fromJson,
  }) async {
    return _makeRequest<T>(
      'POST',
      endpoint,
      headers: headers,
      body: body,
      fromJson: fromJson,
    );
  }

  Future<HttpResponse<T>> _makeRequest<T>(
    String method,
    String endpoint, {
    Map<String, String>? headers,
    Map<String, String>? queryParams,
    Object? body,
    T Function(Map<String, dynamic>)? fromJson,
    List<T> Function(List<dynamic>)? fromJsonList,
  }) async {
    final uri = _buildUri(endpoint, queryParams);
    final spanName = '$method ${uri.path}';
    final span = _tracer.startSpan(spanName);
    span.setAttributes([
      otel.Attribute.fromString('http.request.method', method),
      otel.Attribute.fromString('url.full', uri.toString()),
      otel.Attribute.fromString('url.scheme', uri.scheme),
      otel.Attribute.fromString('url.path', uri.path),
      otel.Attribute.fromString('server.address', uri.host),
      otel.Attribute.fromInt('server.port', uri.port),
      otel.Attribute.fromString('session.id', TelemetryService.instance.sessionId),
    ]);

    final startTime = DateTime.now();
    final traceId = _generateTraceId();
    final currentSpanId = _generateSpanId();

    try {
      final requestHeaders = {
        'Content-Type': 'application/json',
        'User-Agent': '${TelemetryService.serviceName}/${TelemetryService.serviceVersion}',
        'X-Session-ID': TelemetryService.instance.sessionId,
        'traceparent': '00-$traceId-$currentSpanId-01',
        'tracestate': 'astronomy-shop-mobile=session:${TelemetryService.instance.sessionId}',
        ...?headers,
      };

      span.setAttributes([
        otel.Attribute.fromString('trace.id', traceId),
        otel.Attribute.fromString('span.id', currentSpanId),
        otel.Attribute.fromString('trace.propagated', 'true'),
      ]);

      if (kDebugMode) {
        print('$method $uri | traceparent: 00-${traceId.substring(0, 8)}...-${currentSpanId.substring(0, 8)}...-01');
      }

      http.Response response;

      switch (method.toUpperCase()) {
        case 'GET':
          response = await _client.get(uri, headers: requestHeaders);
          break;
        case 'POST':
          final requestBody = body != null ? jsonEncode(body) : null;
          response = await _client.post(
            uri,
            headers: requestHeaders,
            body: requestBody,
          );
          break;
        default:
          throw UnsupportedError('HTTP method $method not supported');
      }

      final endTime = DateTime.now();
      final duration = endTime.difference(startTime);

      span.setAttributes([
        otel.Attribute.fromInt('http.response.status_code', response.statusCode),
        otel.Attribute.fromInt('http.response.body.size', response.bodyBytes.length),
        otel.Attribute.fromInt('http.request.duration_ms', duration.inMilliseconds),
      ]);

      final isSuccess = response.statusCode >= 200 && response.statusCode < 400;

      MetricsService.instance.recordHistogram('http.client.request.duration', duration.inMilliseconds,
        attributes: {'http.request.method': method, 'server.address': uri.host});
      MetricsService.instance.incrementCounter('http.client.request.count',
        attributes: {'http.request.method': method, 'http.response.status_code': '${response.statusCode}'});

      if (response.statusCode >= 500) {
        LogService.instance.error('HTTP $method $uri returned ${response.statusCode}',
          attributes: {'http.request.method': method, 'url.full': uri.toString(), 'http.response.status_code': '${response.statusCode}'});
      } else if (response.statusCode >= 400) {
        LogService.instance.warn('HTTP $method $uri returned ${response.statusCode}',
          attributes: {'http.request.method': method, 'url.full': uri.toString(), 'http.response.status_code': '${response.statusCode}'});
      }

      if (response.statusCode >= 400) {
        span.setAttributes([
          otel.Attribute.fromString('error.type', '${response.statusCode}'),
        ]);
        span.setStatus(otel.StatusCode.error, 'HTTP ${response.statusCode}');
      }

      T? data;
      String? errorMessage;

      if (response.body.isNotEmpty) {
        try {
          final jsonData = jsonDecode(response.body);

          if (fromJsonList != null && jsonData is List) {
            data = fromJsonList(jsonData) as T;
          } else if (fromJson != null && jsonData is Map<String, dynamic>) {
            data = fromJson(jsonData);
          } else if (jsonData is List && T == List) {
            data = jsonData as T;
          } else if (jsonData is Map && T == Map) {
            data = jsonData as T;
          }

          span.addEvent('response_parsed', attributes: [
            otel.Attribute.fromString('response_type', data.runtimeType.toString()),
          ]);

        } catch (e, stackTrace) {
          errorMessage = 'Failed to parse response: $e';
          span.recordException(e, stackTrace: stackTrace);
          span.addEvent('parse_error', attributes: [
            otel.Attribute.fromString('error', e.toString()),
          ]);
        }
      }

      span.end();

      _exportSpanToOTLP(span, traceId, currentSpanId, method, uri, response.statusCode, startTime, endTime, response.bodyBytes.length);

      return HttpResponse<T>(
        statusCode: response.statusCode,
        data: data,
        rawResponse: response.body,
        isSuccess: isSuccess,
        errorMessage: errorMessage,
        duration: duration,
      );

    } catch (e, stackTrace) {
      final endTime = DateTime.now();
      final duration = endTime.difference(startTime);

      span.setAttributes([
        otel.Attribute.fromInt('http.duration_ms', duration.inMilliseconds),
        otel.Attribute.fromString('error.type', e.runtimeType.toString()),
        otel.Attribute.fromString('error.message', e.toString()),
      ]);

      span.recordException(e, stackTrace: stackTrace);
      span.setStatus(otel.StatusCode.error, e.toString());
      span.end();

      MetricsService.instance.recordHistogram('http.client.request.duration', duration.inMilliseconds,
        attributes: {'http.request.method': method, 'server.address': uri.host});
      MetricsService.instance.incrementCounter('http.client.request.count',
        attributes: {'http.request.method': method, 'http.response.status_code': '0'});

      LogService.instance.error(
        'HTTP $method $uri failed: $e',
        exception: e,
        stackTrace: stackTrace,
        attributes: {
          'http.request.method': method,
          'url.full': uri.toString(),
          'duration_ms': duration.inMilliseconds.toString(),
        },
      );

      _exportSpanToOTLP(span, traceId, currentSpanId, method, uri, 0, startTime, endTime, 0);

      return HttpResponse<T>(
        statusCode: 0,
        data: null,
        rawResponse: '',
        isSuccess: false,
        errorMessage: e.toString(),
        duration: duration,
        exception: e,
      );
    }
  }

  Uri _buildUri(String endpoint, Map<String, String>? queryParams) {
    final url = endpoint.startsWith('http') ? endpoint : '$baseUrl$endpoint';
    final uri = Uri.parse(url);

    if (queryParams != null && queryParams.isNotEmpty) {
      return uri.replace(queryParameters: {
        ...uri.queryParameters,
        ...queryParams,
      });
    }

    return uri;
  }

  void dispose() {
    _client.close();
  }

  Future<void> _exportSpanToOTLP(otel.Span span, String traceId, String spanId, String method, Uri uri, int statusCode, DateTime startTime, DateTime endTime, int responseBodySize) async {
    try {
      final startTimeNano = startTime.microsecondsSinceEpoch * 1000;
      final endTimeNano = endTime.microsecondsSinceEpoch * 1000;
      final isError = statusCode == 0 || statusCode >= 400;
      final durationMs = endTime.difference(startTime).inMilliseconds;

      final otlpPayload = {
        'resourceSpans': [
          {
            'resource': {
              'attributes': TelemetryService.instance.getResourceAttributes(),
            },
            'scopeSpans': [
              {
                'scope': {
                  'name': TelemetryService.serviceName,
                  'version': TelemetryService.serviceVersion,
                },
                'spans': [
                  {
                    'traceId': traceId,
                    'spanId': spanId,
                    'name': '$method ${uri.path}',
                    'kind': 3, // SPAN_KIND_CLIENT
                    'startTimeUnixNano': startTimeNano,
                    'endTimeUnixNano': endTimeNano,
                    'attributes': [
                      {'key': 'http.request.method', 'value': {'stringValue': method}},
                      {'key': 'url.full', 'value': {'stringValue': uri.toString()}},
                      {'key': 'url.scheme', 'value': {'stringValue': uri.scheme}},
                      {'key': 'url.path', 'value': {'stringValue': uri.path}},
                      {'key': 'server.address', 'value': {'stringValue': uri.host}},
                      {'key': 'server.port', 'value': {'intValue': uri.port}},
                      {'key': 'http.request.duration_ms', 'value': {'intValue': durationMs}},
                      if (statusCode > 0)
                        {'key': 'http.response.status_code', 'value': {'intValue': statusCode}},
                      if (responseBodySize > 0)
                        {'key': 'http.response.body.size', 'value': {'intValue': responseBodySize}},
                      if (isError)
                        {'key': 'error.type', 'value': {'stringValue': statusCode > 0 ? '$statusCode' : 'network_error'}},
                    ],
                    'status': {'code': isError ? 2 : 1},
                  }
                ]
              }
            ]
          }
        ]
      };

      final headers = <String, String>{
        'Content-Type': 'application/json',
      };

      final token = TelemetryService.instance.accessToken;
      if (token != null) {
        headers['Authorization'] = 'Bearer $token';
      }

      final scoutEndpoint = TelemetryService.scoutEndpoint;
      final endpoint = scoutEndpoint != null && token != null
          ? '$scoutEndpoint/${TelemetryService.otlpTracesExporter}'
          : TelemetryService.otlpTracesEndpoint;

      final response = await _client.post(
        Uri.parse(endpoint),
        headers: headers,
        body: jsonEncode(otlpPayload),
      );

      if (kDebugMode) {
        if (response.statusCode == 200) {
          print('OTLP span sent: $method $uri (trace: ${traceId.substring(0, 8)}...)');
        } else {
          print('OTLP span failed: $method (${response.statusCode})');
        }
      }
    } catch (e) {
      if (kDebugMode) {
        print('OTLP export error: $e');
      }
    }
  }

  String _generateTraceId() {
    final bytes = List.generate(16, (i) => _random.nextInt(256));
    return bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join('');
  }

  String _generateSpanId() {
    final bytes = List.generate(8, (i) => _random.nextInt(256));
    return bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join('');
  }
}

class HttpResponse<T> {
  const HttpResponse({
    required this.statusCode,
    required this.data,
    required this.rawResponse,
    required this.isSuccess,
    this.errorMessage,
    required this.duration,
    this.exception,
  });

  final int statusCode;
  final T? data;
  final String rawResponse;
  final bool isSuccess;
  final String? errorMessage;
  final Duration duration;
  final Object? exception;

  bool get hasError => !isSuccess || errorMessage != null;

  @override
  String toString() {
    return 'HttpResponse{statusCode: $statusCode, success: $isSuccess, '
           'duration: ${duration.inMilliseconds}ms, data: ${data != null ? 'present' : 'null'}}';
  }
}
