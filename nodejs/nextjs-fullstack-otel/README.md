# Next.js OpenTelemetry Sample — Full Stack Instrumentation

A reference implementation showing how to instrument a Next.js App Router application with OpenTelemetry, covering **both server-side and browser-side** telemetry.

## Quick Start (run the sample locally)

```bash
docker compose up --build
```

This starts:
- **Next.js app** at http://localhost:3000
- **OTel Collector** on ports 4317 (gRPC) and 4318 (HTTP)
- **Jaeger UI** at http://localhost:16686

### Testing it

1. Open http://localhost:3000 in your browser
2. Navigate to **Products** — generates server-side SSR + fetch traces
3. Click "Fetch Products (Client-Side)" — generates a browser-side fetch trace
4. Navigate to **Error Demo** and click each button — generates error spans
5. Open http://localhost:16686 (Jaeger) to view traces

**In Jaeger**, look for two services:
- `sample-nextjs-app` — server-side traces
- `sample-nextjs-app-browser` — browser-side traces (errors, web vitals, fetch, page loads)

---

## Integrating Into Your Own App

This guide is organized in levels. Each level builds on the previous one. You can stop at any level and already have value.

### Level 1: Server-Side Auto Instrumentation

**What you get (zero custom code):** automatic tracing of all HTTP requests, Next.js SSR rendering, server-side fetch calls, API route execution, plus metrics.

| What | How | Automatic? |
|------|-----|------------|
| Incoming HTTP requests | `auto-instrumentations-node` | Yes |
| SSR rendering spans | Next.js built-in OTel | Yes |
| Server-side fetch calls | Next.js built-in OTel | Yes |
| API route execution | Next.js built-in OTel | Yes |
| HTTP metrics (counts, durations) | `sdk-metrics` + auto-instrumentations | Yes |

**Install packages:**

```bash
npm install \
  @opentelemetry/api \
  @opentelemetry/sdk-node \
  @opentelemetry/auto-instrumentations-node \
  @opentelemetry/exporter-trace-otlp-http \
  @opentelemetry/exporter-metrics-otlp-http \
  @opentelemetry/exporter-logs-otlp-http \
  @opentelemetry/resources \
  @opentelemetry/semantic-conventions \
  @opentelemetry/sdk-metrics \
  @opentelemetry/sdk-trace-base \
  @opentelemetry/sdk-logs \
  @opentelemetry/api-logs
```

**Create `instrumentation.ts`** in your project root (next to `package.json`):

```ts
export async function register() {
  if (process.env.NEXT_RUNTIME === 'nodejs') {
    await import('./src/lib/server-telemetry');
  }
}
```

**Create `src/lib/server-telemetry.ts`:**

See [`src/lib/server-telemetry.ts`](src/lib/server-telemetry.ts) in this repo for the full file. Key points:
- Uses `NodeSDK` with `getNodeAutoInstrumentations()` — this is what auto-instruments everything
- Configures `BatchSpanProcessor` for traces, `PeriodicExportingMetricReader` for metrics, `BatchLogRecordProcessor` for logs
- Disables noisy instrumentations (`fs`, `dns`, `net`) to reduce noise
- Filters out `/_next/*` static asset requests from tracing

**Set environment variables:**

```env
OTEL_EXPORTER_OTLP_ENDPOINT=http://your-collector:4318
OTEL_SERVICE_NAME=your-app-name
```

**That's it.** All HTTP requests, SSR renders, fetch calls, and API routes are now automatically traced with zero custom code.

---

### Level 2: Server-Side Console Log Capture

**What you get:** all `console.log`, `console.warn`, and `console.error` output from the server is captured as OTel log records — including Next.js internal error output like `⨯ Error: useMediaQuery is a client-only hook` that happens during SSR.

**No extra packages needed.** This is a console bridge added to `server-telemetry.ts`. It intercepts the global `console` methods and also emits OTel log records.

The bridge is already included in the [`server-telemetry.ts`](src/lib/server-telemetry.ts) in this repo. The relevant section:

```ts
import { logs, SeverityNumber } from '@opentelemetry/api-logs';
import { LoggerProvider } from '@opentelemetry/sdk-logs';

// After sdk.start():
const loggerProvider = logs.getLoggerProvider() as LoggerProvider;
const otelLogger = loggerProvider.getLogger('console-bridge');

const originalConsoleError = console.error;
console.error = (...args: unknown[]) => {
  originalConsoleError.apply(console, args);
  otelLogger.emit({
    severityNumber: SeverityNumber.ERROR,
    severityText: 'ERROR',
    body: args.map(String).join(' '),
    attributes: { 'log.source': 'console.error' },
  });
};
// Same pattern for console.log (INFO) and console.warn (WARN)
```

Each captured log gets:
- Proper `SeverityText` / `SeverityNumber` (INFO for `.log`, WARN for `.warn`, ERROR for `.error`)
- A `log.source` attribute identifying which console method produced it
- Trace ID correlation (if the console call happens within a traced request)

**No code changes in your app needed** — existing `console.log/warn/error` calls are automatically captured.

---

### Level 3: Browser-Side Auto Instrumentation

**What you get (zero custom code beyond setup):** automatic tracing of page loads, client-side fetch/XHR requests, and user interactions (clicks, form submissions) in the browser.

| What | How | Automatic? |
|------|-----|------------|
| Page load timing | `instrumentation-document-load` | Yes |
| Client-side fetch/XHR | `instrumentation-fetch` | Yes |
| User clicks & form submits | `instrumentation-user-interaction` | Yes |

**Install packages:**

```bash
npm install \
  @opentelemetry/sdk-trace-web \
  @opentelemetry/sdk-trace-base \
  @opentelemetry/auto-instrumentations-web \
  @opentelemetry/context-zone \
  @opentelemetry/instrumentation \
  @opentelemetry/exporter-trace-otlp-http \
  @opentelemetry/resources \
  @opentelemetry/semantic-conventions
```

**Create `src/lib/browser-telemetry.ts`:**

See [`src/lib/browser-telemetry.ts`](src/lib/browser-telemetry.ts) in this repo. For Level 3, the key part is the auto-instrumentation setup:

```ts
'use client';

import { WebTracerProvider } from '@opentelemetry/sdk-trace-web';
import { BatchSpanProcessor } from '@opentelemetry/sdk-trace-base';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import { resourceFromAttributes } from '@opentelemetry/resources';
import { ATTR_SERVICE_NAME } from '@opentelemetry/semantic-conventions';
import { ZoneContextManager } from '@opentelemetry/context-zone';
import { registerInstrumentations } from '@opentelemetry/instrumentation';
import { getWebAutoInstrumentations } from '@opentelemetry/auto-instrumentations-web';

let initialized = false;

export function initBrowserTelemetry() {
  if (initialized || typeof window === 'undefined') return;
  initialized = true;

  const OTEL_ENDPOINT = process.env.NEXT_PUBLIC_OTEL_ENDPOINT || '/api/otel';

  const provider = new WebTracerProvider({
    resource: resourceFromAttributes({
      [ATTR_SERVICE_NAME]: process.env.NEXT_PUBLIC_OTEL_SERVICE_NAME || 'your-app-browser',
    }),
    spanProcessors: [
      new BatchSpanProcessor(new OTLPTraceExporter({ url: `${OTEL_ENDPOINT}/v1/traces` })),
    ],
  });

  provider.register({ contextManager: new ZoneContextManager() });

  registerInstrumentations({
    instrumentations: [
      getWebAutoInstrumentations({
        '@opentelemetry/instrumentation-document-load': {},
        '@opentelemetry/instrumentation-user-interaction': { eventNames: ['click', 'submit'] },
        '@opentelemetry/instrumentation-fetch': { propagateTraceHeaderCorsUrls: [/.*/] },
        '@opentelemetry/instrumentation-xml-http-request': { propagateTraceHeaderCorsUrls: [/.*/] },
      }),
    ],
  });
}
```

**Create `src/components/TelemetryProvider.tsx`:**

```tsx
'use client';

import { useEffect } from 'react';
import { initBrowserTelemetry } from '@/lib/browser-telemetry';

export default function TelemetryProvider({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    initBrowserTelemetry();
  }, []);

  return <>{children}</>;
}
```

**Wrap your root layout** — in `src/app/layout.tsx`:

```tsx
import TelemetryProvider from '@/components/TelemetryProvider';

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <TelemetryProvider>
          {children}
        </TelemetryProvider>
      </body>
    </html>
  );
}
```

**Create the telemetry proxy route** — `src/app/api/otel/[...signal]/route.ts`:

This proxies browser telemetry through your Next.js server to the collector, so you don't need CORS config on the collector.

```ts
import { NextRequest, NextResponse } from 'next/server';

const COLLECTOR_ENDPOINT = process.env.OTEL_EXPORTER_OTLP_ENDPOINT || 'http://localhost:4318';

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ signal: string[] }> }
) {
  const { signal } = await params;
  const path = signal.join('/');
  const body = await request.arrayBuffer();

  const response = await fetch(`${COLLECTOR_ENDPOINT}/${path}`, {
    method: 'POST',
    headers: { 'Content-Type': request.headers.get('Content-Type') || 'application/json' },
    body,
  });

  return new NextResponse(response.body, {
    status: response.status,
    headers: { 'Content-Type': response.headers.get('Content-Type') || 'application/json' },
  });
}
```

**Set environment variable:**

```env
NEXT_PUBLIC_OTEL_SERVICE_NAME=your-app-name-browser
```

---

### Level 4: Browser Error Capture

**What you get:** uncaught JS errors, unhandled promise rejections, and browser `console.warn`/`console.error` output captured as OTel spans.

| What | Span Name | Custom code? |
|------|-----------|-------------|
| Uncaught JS errors (TypeError, ReferenceError, etc.) | `browser.error` | Yes — `window.addEventListener('error')` |
| Unhandled promise rejections | `browser.unhandled_rejection` | Yes — `window.addEventListener('unhandledrejection')` |
| `console.warn(...)` in browser | `browser.console.warn` | Yes — console bridge |
| `console.error(...)` in browser | `browser.console.error` | Yes — console bridge |

These are all included in the full [`browser-telemetry.ts`](src/lib/browser-telemetry.ts) in this repo. Add these functions and call them from `initBrowserTelemetry()`:

**Error handlers** — add `setupErrorHandlers()`:

```ts
import { trace, SpanStatusCode } from '@opentelemetry/api';

function setupErrorHandlers() {
  const tracer = trace.getTracer('browser-errors');

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

  window.addEventListener('unhandledrejection', (event) => {
    const reason = event.reason;
    const message = reason instanceof Error ? reason.message : String(reason);
    tracer.startActiveSpan('browser.unhandled_rejection', (span) => {
      span.setStatus({ code: SpanStatusCode.ERROR, message });
      span.setAttributes({
        'error.type': reason?.name || 'UnhandledRejection',
        'error.message': message,
        'error.stack': reason instanceof Error ? reason.stack || '' : '',
        'page.url': window.location.href,
        'page.path': window.location.pathname,
      });
      span.end();
    });
  });
}
```

**Console bridge** — add `setupConsoleBridge()`:

```ts
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
```

Call both from `initBrowserTelemetry()`:

```ts
export function initBrowserTelemetry() {
  // ... Level 3 setup ...
  setupErrorHandlers();
  setupConsoleBridge();
}
```

---

### Level 5: React Error Boundaries + Web Vitals

**React error boundaries** — Next.js `error.tsx` files catch component render crashes. Add OTel reporting to them.

Export `reportErrorBoundary()` from `browser-telemetry.ts`:

```ts
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
```

Create `src/app/error.tsx` (and/or `src/app/global-error.tsx`):

```tsx
'use client';

import { useEffect } from 'react';
import { reportErrorBoundary } from '@/lib/browser-telemetry';

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    reportErrorBoundary(error);
  }, [error]);

  return (
    <div>
      <h2>Something went wrong</h2>
      <button onClick={reset}>Try Again</button>
    </div>
  );
}
```

You can add `error.tsx` at any route level for granular crash reporting.

**Web Vitals** — install the library and add reporting:

```bash
npm install web-vitals
```

Add `setupWebVitals()` to `browser-telemetry.ts`:

```ts
import { onCLS, onLCP, onTTFB, onINP } from 'web-vitals';

function setupWebVitals() {
  const tracer = trace.getTracer('web-vitals');

  function reportVital(metric: { name: string; value: number; rating: string; id: string }) {
    tracer.startActiveSpan(`web-vital.${metric.name}`, (span) => {
      span.setAttributes({
        'web_vital.name': metric.name,
        'web_vital.value': metric.value,
        'web_vital.rating': metric.rating,
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
```

Call from `initBrowserTelemetry()`:

```ts
export function initBrowserTelemetry() {
  // ... Level 3 + Level 4 setup ...
  setupWebVitals();
}
```

Reports `web-vital.LCP`, `web-vital.CLS`, `web-vital.INP`, `web-vital.TTFB` with value and rating (good / needs-improvement / poor).

---

### Level 6: Structured Server-Side Logs (optional)

Level 2 captures all console output as OTel logs, but they're just string bodies. For new code, use the OTel Logs API directly to emit structured logs with typed attributes for better filtering.

**Create `src/lib/logger.ts`:**

```ts
import { logs, SeverityNumber } from '@opentelemetry/api-logs';

const logger = logs.getLogger('your-app-name');

export function logInfo(message: string, attributes?: Record<string, string | number | boolean>) {
  logger.emit({ severityNumber: SeverityNumber.INFO, severityText: 'INFO', body: message, attributes });
}

export function logError(message: string, attributes?: Record<string, string | number | boolean>) {
  logger.emit({ severityNumber: SeverityNumber.ERROR, severityText: 'ERROR', body: message, attributes });
}

export function logWarn(message: string, attributes?: Record<string, string | number | boolean>) {
  logger.emit({ severityNumber: SeverityNumber.WARN, severityText: 'WARN', body: message, attributes });
}
```

**Use in your code:**

```ts
import { logInfo, logError } from '@/lib/logger';

logInfo('Products fetched', { 'products.count': 5 });
logError('Payment failed', { 'order.id': 'ORD-123', 'error.code': 'TIMEOUT' });
```

---

## Summary: What Each Level Gives You

| Level | What | Custom code? | Effort |
|-------|------|-------------|--------|
| **1** | Server traces + metrics (HTTP, SSR, fetch, API routes) | No — auto | Install packages + 2 files |
| **2** | Server console.log/warn/error as OTel logs | Minimal — console bridge | Add to server-telemetry.ts |
| **3** | Browser page loads, fetch/XHR, clicks | No — auto | Install packages + 3 files |
| **4** | Browser JS errors, promise rejections, console.warn/error | Yes — event listeners + console bridge | Add to browser-telemetry.ts |
| **5** | React crash reporting + Core Web Vitals | Yes — error boundaries + web-vitals | Add error.tsx + setupWebVitals |
| **6** | Structured server logs with typed attributes | Yes — logger utility | Optional, for new code |

---

## Project Structure

```
sample-nextjs-otel/
├── instrumentation.ts              # Next.js entry — loads server OTel
├── src/
│   ├── lib/
│   │   ├── server-telemetry.ts     # Server: NodeSDK + auto-instrumentations + console bridge
│   │   ├── browser-telemetry.ts    # Browser: auto-instrumentations + errors + web vitals + console bridge
│   │   └── logger.ts              # Structured OTel log helper (Level 6)
│   ├── components/
│   │   └── TelemetryProvider.tsx   # Client component that initializes browser OTel
│   └── app/
│       ├── layout.tsx              # Root layout — wraps app in TelemetryProvider
│       ├── global-error.tsx        # Root error boundary → reports to OTel
│       ├── products/               # SSR page + client-side fetch demo
│       ├── error-demo/             # Error trigger buttons + error boundary
│       └── api/
│           ├── products/route.ts   # Sample API route
│           ├── error/route.ts      # Intentional error API route
│           └── otel/[...signal]/route.ts  # Browser telemetry proxy
├── config/
│   └── otel-collector.yaml         # Collector config
├── docker-compose.yml
├── Dockerfile
└── .env
```

## Environment Variables

| Variable | Where | Default | Description |
|----------|-------|---------|-------------|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Server | `http://localhost:4318` | Collector OTLP HTTP endpoint |
| `OTEL_SERVICE_NAME` | Server | `sample-nextjs-app` | Service name for server traces |
| `NEXT_PUBLIC_OTEL_ENDPOINT` | Browser | `/api/otel` (proxy) | Where browser sends telemetry |
| `NEXT_PUBLIC_OTEL_SERVICE_NAME` | Browser | `sample-nextjs-app-browser` | Service name for browser traces |
