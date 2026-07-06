import { metrics, type Histogram } from '@opentelemetry/api';
import { onCLS, onFCP, onINP, onLCP, onTTFB, type Metric } from 'web-vitals';

// Web Vitals as histograms (not spans) so RUM can report p75/p95; one instrument
// per vital for per-vital bucket Views (see browser-telemetry.ts).
export function setupWebVitals(): void {
  // Acquire after the global MeterProvider is set (else Noop meter, dropped).
  const meter = metrics.getMeter('web-vitals', '1.0.0');

  const cls = meter.createHistogram('web_vitals.cls', {
    unit: '1',
    description: 'Cumulative Layout Shift',
  });
  const lcp = meter.createHistogram('web_vitals.lcp', {
    unit: 'ms',
    description: 'Largest Contentful Paint',
  });
  const inp = meter.createHistogram('web_vitals.inp', {
    unit: 'ms',
    description: 'Interaction to Next Paint',
  });
  const fcp = meter.createHistogram('web_vitals.fcp', {
    unit: 'ms',
    description: 'First Contentful Paint',
  });
  const ttfb = meter.createHistogram('web_vitals.ttfb', {
    unit: 'ms',
    description: 'Time to First Byte',
  });

  const record =
    (histogram: Histogram) =>
    (metric: Metric): void => {
      histogram.record(metric.value, {
        'web_vital.rating': metric.rating,
        'page.path': window.location.pathname,
      });
    };

  onCLS(record(cls));
  onLCP(record(lcp));
  onINP(record(inp));
  onFCP(record(fcp));
  onTTFB(record(ttfb));
}
