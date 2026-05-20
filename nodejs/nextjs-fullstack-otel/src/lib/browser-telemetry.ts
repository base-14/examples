'use client';

import { WebTracerProvider } from '@opentelemetry/sdk-trace-web';
import { BatchSpanProcessor } from '@opentelemetry/sdk-trace-base';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import { resourceFromAttributes } from '@opentelemetry/resources';
import { ATTR_SERVICE_NAME, ATTR_SERVICE_VERSION } from '@opentelemetry/semantic-conventions';
import { ZoneContextManager } from '@opentelemetry/context-zone';
import { registerInstrumentations } from '@opentelemetry/instrumentation';
import { getWebAutoInstrumentations } from '@opentelemetry/auto-instrumentations-web';
import { trace, SpanStatusCode } from '@opentelemetry/api';
import { onCLS, onLCP, onTTFB, onINP } from 'web-vitals';

let initialized = false;

export function initBrowserTelemetry() {
  if (initialized || typeof window === 'undefined') return;
  initialized = true;

  // Use the Next.js API proxy by default — no CORS config needed on collector.
  // Set NEXT_PUBLIC_OTEL_ENDPOINT to send directly to collector instead (requires CORS).
  const OTEL_ENDPOINT = process.env.NEXT_PUBLIC_OTEL_ENDPOINT || '/api/otel';

  // --- 1. Trace Provider ---
  const resource = resourceFromAttributes({
    [ATTR_SERVICE_NAME]: process.env.NEXT_PUBLIC_OTEL_SERVICE_NAME || 'sample-nextjs-app-browser',
    [ATTR_SERVICE_VERSION]: '1.0.0',
    'deployment.environment': process.env.NODE_ENV || 'development',
    'telemetry.sdk.language': 'webjs',
  });

  const traceExporter = new OTLPTraceExporter({
    url: `${OTEL_ENDPOINT}/v1/traces`,
  });

  const provider = new WebTracerProvider({
    resource,
    spanProcessors: [new BatchSpanProcessor(traceExporter)],
  });

  provider.register({
    contextManager: new ZoneContextManager(),
  });

  // --- 2. Auto-Instrumentations (fetch, XHR, document load, user interaction) ---
  registerInstrumentations({
    instrumentations: [
      getWebAutoInstrumentations({
        '@opentelemetry/instrumentation-document-load': {},
        '@opentelemetry/instrumentation-user-interaction': {
          eventNames: ['click', 'submit'],
        },
        '@opentelemetry/instrumentation-fetch': {
          propagateTraceHeaderCorsUrls: [/.*/],
        },
        '@opentelemetry/instrumentation-xml-http-request': {
          propagateTraceHeaderCorsUrls: [/.*/],
        },
      }),
    ],
  });

  // --- 3. Global Error Handlers (browser JS errors + unhandled rejections) ---
  setupErrorHandlers();

  // --- 4. Web Vitals ---
  setupWebVitals();

  // --- 5. Console bridge (captures console.warn/error in the browser) ---
  setupConsoleBridge();

  console.log(`[OTel] Browser-side instrumentation initialized — exporting to ${OTEL_ENDPOINT}`);
}

// ============================================================
// Browser Error Capture
// ============================================================

function setupErrorHandlers() {
  const tracer = trace.getTracer('browser-errors');

  // Catch uncaught JS errors (e.g., TypeError, ReferenceError thrown in event handlers)
  window.addEventListener('error', (event) => {
    tracer.startActiveSpan('browser.error', (span) => {
      span.setStatus({ code: SpanStatusCode.ERROR, message: event.message });
      span.setAttributes({
        'error.type': event.error?.name || 'Error',
        'error.message': event.message,
        'error.stack': event.error?.stack || '',
        'error.filename': event.filename || '',
        'error.lineno': event.lineno || 0,
        'error.colno': event.colno || 0,
        'page.url': window.location.href,
        'page.path': window.location.pathname,
      });
      span.end();
    });
  });

  // Catch unhandled promise rejections
  window.addEventListener('unhandledrejection', (event) => {
    const reason = event.reason;
    const message = reason instanceof Error ? reason.message : String(reason);
    const stack = reason instanceof Error ? reason.stack : '';

    tracer.startActiveSpan('browser.unhandled_rejection', (span) => {
      span.setStatus({ code: SpanStatusCode.ERROR, message });
      span.setAttributes({
        'error.type': reason?.name || 'UnhandledRejection',
        'error.message': message,
        'error.stack': stack || '',
        'page.url': window.location.href,
        'page.path': window.location.pathname,
      });
      span.end();
    });
  });
}

// ============================================================
// Web Vitals → OTel Spans
// ============================================================

function setupWebVitals() {
  const tracer = trace.getTracer('web-vitals');

  function reportVital(metric: { name: string; value: number; rating: string; id: string }) {
    tracer.startActiveSpan(`web-vital.${metric.name}`, (span) => {
      span.setAttributes({
        'web_vital.name': metric.name,
        'web_vital.value': metric.value,
        'web_vital.rating': metric.rating, // "good", "needs-improvement", or "poor"
        'web_vital.id': metric.id,
        'page.url': window.location.href,
        'page.path': window.location.pathname,
      });
      span.end();
    });
  }

  onCLS(reportVital);
  onLCP(reportVital);
  onTTFB(reportVital);
  onINP(reportVital);
}

// ============================================================
// Browser Console Bridge — captures console.warn/error as spans
// ============================================================

function setupConsoleBridge() {
  const tracer = trace.getTracer('browser-console');

  const originalWarn = console.warn;
  const originalError = console.error;

  console.warn = (...args: unknown[]) => {
    originalWarn.apply(console, args);
    tracer.startActiveSpan('browser.console.warn', (span) => {
      span.setAttributes({
        'log.source': 'console.warn',
        'log.message': args.map(String).join(' '),
        'page.url': window.location.href,
        'page.path': window.location.pathname,
      });
      span.end();
    });
  };

  console.error = (...args: unknown[]) => {
    originalError.apply(console, args);
    tracer.startActiveSpan('browser.console.error', (span) => {
      span.setStatus({ code: SpanStatusCode.ERROR, message: args.map(String).join(' ').slice(0, 200) });
      span.setAttributes({
        'log.source': 'console.error',
        'log.message': args.map(String).join(' '),
        'page.url': window.location.href,
        'page.path': window.location.pathname,
      });
      span.end();
    });
  };
}

// ============================================================
// Helper: report React Error Boundary errors to OTel
// ============================================================

export function reportErrorBoundary(error: Error, componentStack?: string) {
  const tracer = trace.getTracer('browser-errors');

  tracer.startActiveSpan('browser.react_error_boundary', (span) => {
    span.setStatus({ code: SpanStatusCode.ERROR, message: error.message });
    span.setAttributes({
      'error.type': error.name || 'ReactError',
      'error.message': error.message,
      'error.stack': error.stack || '',
      'error.component_stack': componentStack || '',
      'page.url': typeof window !== 'undefined' ? window.location.href : '',
      'page.path': typeof window !== 'undefined' ? window.location.pathname : '',
    });
    span.end();
  });
}
