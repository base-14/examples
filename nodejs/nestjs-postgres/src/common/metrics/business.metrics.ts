import { metrics } from '@opentelemetry/api';

const meter = metrics.getMeter('websocket-metrics');

/**
 * WebSocket-specific metrics for real-time event tracking.
 * Other business metrics are defined in their respective services:
 * - auth.service.ts: auth.registration.total, auth.login.success, auth.login.attempts
 * - articles.service.ts: articles.created
 * - favorites.service.ts: articles.favorited
 * - notification.processor.ts: articles.published, jobs.completed, jobs.failed, jobs.duration
 * - job-metrics.service.ts: job_queue_waiting, job_queue_active, job_queue_failed
 * - http-exception.filter.ts: http_errors_total
 */
export const BusinessMetrics = {
  websocketConnections: meter.createUpDownCounter('websocket_connections', {
    description: 'Active WebSocket connections',
  }),

  websocketEvents: meter.createCounter('websocket_events_total', {
    description: 'Total WebSocket events emitted by type',
  }),
};
