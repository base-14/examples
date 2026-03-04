// Copyright 2020 The Flutter team. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import 'package:flutterrific_opentelemetry/flutterrific_opentelemetry.dart';
// ignore: depend_on_referenced_packages
import 'package:http/http.dart' as http;

import 'rum_session.dart';

/// Instrumented HTTP client — drop-in replacement for [http.Client].
///
/// Creates OTel spans around every HTTP request with method, URL, status code,
/// and size attributes. Injects W3C `traceparent` header for distributed
/// tracing. RUM context (session, user, screen) is automatically added by
/// [RumSpanProcessor].
///
/// Usage:
/// ```dart
/// final client = RumHttpClient();
/// final response = await client.get(Uri.parse('https://api.example.com/data'));
/// ```
class RumHttpClient extends http.BaseClient {
  RumHttpClient([http.Client? inner]) : _inner = inner ?? http.Client();

  final http.Client _inner;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    final tracer = FlutterOTel.tracer;
    final span = tracer.startSpan('http.${request.method.toLowerCase()}');

    span.setStringAttribute<String>('http.request.method', request.method);
    span.setStringAttribute<String>('url.full', request.url.toString());
    span.setStringAttribute<String>('server.address', request.url.host);
    span.setStringAttribute<String>('url.path', request.url.path);
    if (request.contentLength != null && request.contentLength! > 0) {
      span.setIntAttribute(
          'http.request.body.size', request.contentLength!);
    }

    // W3C Trace Context propagation — inject traceparent header
    // Format: version-traceId-spanId-traceFlags (00-{32hex}-{16hex}-01)
    final traceId = span.spanContext.traceId.hexString;
    final spanId = span.spanContext.spanId.hexString;
    request.headers['traceparent'] = '00-$traceId-$spanId-01';
    request.headers['tracestate'] = '';

    // Record breadcrumb for this HTTP request
    RumSession.instance.recordBreadcrumb(
      'http',
      '${request.method} ${request.url.host}${request.url.path}',
    );

    try {
      final response = await _inner.send(request);

      span.setIntAttribute('http.response.status_code', response.statusCode);
      if (response.contentLength != null) {
        span.setIntAttribute(
            'http.response.body.size', response.contentLength!);
      }

      if (response.statusCode >= 400) {
        span.setStatus(
          SpanStatusCode.Error,
          'HTTP ${response.statusCode} ${response.reasonPhrase}',
        );
      }

      span.end();
      return response;
    } catch (error, stackTrace) {
      span.setStringAttribute<String>(
          'error.type', error.runtimeType.toString());
      span.setStringAttribute<String>('error.message', error.toString());
      span.setStatus(SpanStatusCode.Error, error.toString());

      FlutterOTel.reportError(
        'HTTP request failed: ${request.method} ${request.url}',
        error,
        stackTrace,
      );

      span.end();
      rethrow;
    }
  }

  @override
  void close() {
    _inner.close();
    super.close();
  }
}
