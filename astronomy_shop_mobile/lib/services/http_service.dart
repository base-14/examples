import 'dart:convert';
import 'dart:math';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:opentelemetry/api.dart' as otel;
import 'telemetry_service.dart';
import 'config_service.dart';

class HttpService {
  static HttpService? _instance;

  late final otel.Tracer _tracer;
  late final http.Client _client;
  late final ConfigService _config;

  HttpService._internal() {
    _tracer = TelemetryService.instance.tracer;
    _client = http.Client();
    _config = ConfigService.instance;
  }

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
    final span = _tracer.startSpan('http_request');
    span.setAttributes([
      otel.Attribute.fromString('http.method', method),
      otel.Attribute.fromString('http.url', uri.toString()),
      otel.Attribute.fromString('http.scheme', uri.scheme),
      otel.Attribute.fromString('http.host', uri.host),
      otel.Attribute.fromInt('http.port', uri.port),
      otel.Attribute.fromString('http.target', uri.path),
      otel.Attribute.fromString('session.id', TelemetryService.instance.sessionId),
      otel.Attribute.fromString('user_agent', '${TelemetryService.serviceName}/${TelemetryService.serviceVersion}'),
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
        otel.Attribute.fromInt('http.status_code', response.statusCode),
        otel.Attribute.fromInt('http.response_size', response.body.length),
        otel.Attribute.fromInt('http.duration_ms', duration.inMilliseconds),
      ]);
      
      final isSuccess = response.statusCode >= 200 && response.statusCode < 300;
      
      if (isSuccess) {
        span.setStatus(otel.StatusCode.ok);
      } else {
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
      
      _exportSpanToOTLP(span, traceId, currentSpanId, startTime, endTime);
      
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
      
      _exportSpanToOTLP(span, traceId, currentSpanId, startTime, endTime);
      
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
  
  Future<void> _exportSpanToOTLP(otel.Span span, String traceId, String spanId, DateTime startTime, DateTime endTime) async {
    try {
      final startTimeNano = startTime.microsecondsSinceEpoch * 1000;
      final endTimeNano = endTime.microsecondsSinceEpoch * 1000;
      
      final otlpPayload = {
        'resourceSpans': [
          {
            'resource': {
              'attributes': [
                {'key': 'service.name', 'value': {'stringValue': TelemetryService.serviceName}},
                {'key': 'service.version', 'value': {'stringValue': TelemetryService.serviceVersion}},
                {'key': 'telemetry.sdk.name', 'value': {'stringValue': 'flutter-opentelemetry'}},
                {'key': 'session.id', 'value': {'stringValue': TelemetryService.instance.sessionId}},
                {'key': 'deployment.environment', 'value': {'stringValue': TelemetryService.environment}},
              ],
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
                    'name': 'http_request',
                    'kind': 3, // SPAN_KIND_CLIENT
                    'startTimeUnixNano': startTimeNano,
                    'endTimeUnixNano': endTimeNano,
                    'attributes': [
                      {'key': 'http.method', 'value': {'stringValue': 'HTTP'}},
                      {'key': 'http.url', 'value': {'stringValue': 'API Request'}},
                      {'key': 'component', 'value': {'stringValue': 'http_client'}},
                      {'key': 'span.kind', 'value': {'stringValue': 'client'}},
                    ],
                  }
                ]
              }
            ]
          }
        ]
      };
      
      final response = await _client.post(
        Uri.parse(TelemetryService.otlpTracesEndpoint),
        headers: {
          'Content-Type': 'application/json',
        },
        body: jsonEncode(otlpPayload),
      );
      
      if (response.statusCode == 200) {
      }
    } catch (e) {
      // Ignore export errors
    }
  }
  
  String _generateTraceId() {
    final random = Random.secure();
    final bytes = List.generate(16, (i) => random.nextInt(256));
    final traceId = bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join('');
    return traceId;
  }
  
  String _generateSpanId() {
    final random = Random.secure();
    final bytes = List.generate(8, (i) => random.nextInt(256));
    final spanId = bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join('');
    return spanId;
  }
}

class HttpResponse<T> {
  final int statusCode;
  final T? data;
  final String rawResponse;
  final bool isSuccess;
  final String? errorMessage;
  final Duration duration;
  final Object? exception;
  
  const HttpResponse({
    required this.statusCode,
    required this.data,
    required this.rawResponse,
    required this.isSuccess,
    this.errorMessage,
    required this.duration,
    this.exception,
  });
  
  bool get hasError => !isSuccess || errorMessage != null;
  
  @override
  String toString() {
    return 'HttpResponse{statusCode: $statusCode, success: $isSuccess, '
           'duration: ${duration.inMilliseconds}ms, data: ${data != null ? 'present' : 'null'}}';
  }
}