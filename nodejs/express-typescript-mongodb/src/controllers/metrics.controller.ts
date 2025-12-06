import type { Request, Response, NextFunction } from 'express';
import { metrics } from '@opentelemetry/api';

export async function getMetrics(
  _req: Request,
  res: Response,
  next: NextFunction
): Promise<void> {
  try {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const meterProvider = (metrics as any).getMeterProvider?.();

    if (!meterProvider) {
      res.status(503).json({ error: 'Metrics not available' });
      return;
    }

    const prometheusMetrics: string[] = [
      '# HELP articles_created_total Total number of articles created',
      '# TYPE articles_created_total counter',
      '# HELP articles_published_total Total number of articles published',
      '# TYPE articles_published_total counter',
      '# HELP articles_deleted_total Total number of articles deleted',
      '# TYPE articles_deleted_total counter',
      '# HELP articles_favorited_total Total number of article favorites',
      '# TYPE articles_favorited_total counter',
      '# HELP articles_unfavorited_total Total number of article unfavorites',
      '# TYPE articles_unfavorited_total counter',
      '# HELP articles_total Current total number of articles in database',
      '# TYPE articles_total gauge',
      '# HELP article_content_size_characters Size of article content in characters',
      '# TYPE article_content_size_characters histogram',
      '# HELP article_publish_duration_milliseconds Duration of article publish job processing',
      '# TYPE article_publish_duration_milliseconds histogram',
      '',
      '# HELP users_registered_total Total number of user registrations',
      '# TYPE users_registered_total counter',
      '# HELP users_login_success_total Total number of successful login attempts',
      '# TYPE users_login_success_total counter',
      '# HELP users_login_failed_total Total number of failed login attempts',
      '# TYPE users_login_failed_total counter',
      '# HELP users_logout_total Total number of user logouts',
      '# TYPE users_logout_total counter',
      '# HELP users_active_total Total number of registered users',
      '# TYPE users_active_total gauge',
      '',
      '# HELP jobs_enqueued_total Total number of jobs enqueued',
      '# TYPE jobs_enqueued_total counter',
      '# HELP jobs_completed_total Total number of jobs completed successfully',
      '# TYPE jobs_completed_total counter',
      '# HELP jobs_failed_total Total number of jobs that failed',
      '# TYPE jobs_failed_total counter',
      '# HELP jobs_processing_duration_milliseconds Duration of job processing',
      '# TYPE jobs_processing_duration_milliseconds histogram',
      '',
      '# HELP api_requests_total Total number of API requests by endpoint and status',
      '# TYPE api_requests_total counter',
      '# HELP api_response_time_milliseconds API response time by endpoint',
      '# TYPE api_response_time_milliseconds histogram',
      '',
      '# OpenTelemetry metrics are exported via OTLP HTTP to the collector',
      '# This endpoint provides Prometheus-compatible metric definitions',
      '# Actual metric values are collected by the OpenTelemetry SDK',
    ];

    res.set('Content-Type', 'text/plain; version=0.0.4');
    res.send(prometheusMetrics.join('\n'));
  } catch (error) {
    next(error);
  }
}
