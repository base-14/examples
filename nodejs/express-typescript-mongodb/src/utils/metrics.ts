import { metrics } from '@opentelemetry/api';
import { config } from '../config.js';

const meter = metrics.getMeter(config.otel.serviceName, config.app.version);

export const articleMetrics = {
  created: meter.createCounter('articles.created.total', {
    description: 'Total number of articles created',
    unit: '1',
  }),

  published: meter.createCounter('articles.published.total', {
    description: 'Total number of articles published',
    unit: '1',
  }),

  deleted: meter.createCounter('articles.deleted.total', {
    description: 'Total number of articles deleted',
    unit: '1',
  }),

  publishDuration: meter.createHistogram('article.publish.duration', {
    description: 'Duration of article publish job processing',
    unit: 'ms',
  }),

  contentSize: meter.createHistogram('article.content.size', {
    description: 'Size of article content in characters',
    unit: 'characters',
  }),

  total: meter.createUpDownCounter('articles.total', {
    description: 'Current total number of articles in database',
    unit: '1',
  }),

  favorited: meter.createCounter('articles.favorited.total', {
    description: 'Total number of article favorites',
    unit: '1',
  }),

  unfavorited: meter.createCounter('articles.unfavorited.total', {
    description: 'Total number of article unfavorites',
    unit: '1',
  }),
};

export const authMetrics = {
  registrations: meter.createCounter('users.registered.total', {
    description: 'Total number of user registrations',
    unit: '1',
  }),

  loginSuccess: meter.createCounter('users.login.success.total', {
    description: 'Total number of successful login attempts',
    unit: '1',
  }),

  loginFailed: meter.createCounter('users.login.failed.total', {
    description: 'Total number of failed login attempts',
    unit: '1',
  }),

  activeUsers: meter.createUpDownCounter('users.active.total', {
    description: 'Total number of registered users',
    unit: '1',
  }),

  logout: meter.createCounter('users.logout.total', {
    description: 'Total number of user logouts',
    unit: '1',
  }),
};

export const jobMetrics = {
  enqueued: meter.createCounter('jobs.enqueued.total', {
    description: 'Total number of jobs enqueued',
    unit: '1',
  }),

  completed: meter.createCounter('jobs.completed.total', {
    description: 'Total number of jobs completed successfully',
    unit: '1',
  }),

  failed: meter.createCounter('jobs.failed.total', {
    description: 'Total number of jobs that failed',
    unit: '1',
  }),

  processingTime: meter.createHistogram('jobs.processing.duration', {
    description: 'Duration of job processing',
    unit: 'ms',
  }),
};

export const apiMetrics = {
  requestsTotal: meter.createCounter('api.requests.total', {
    description: 'Total number of API requests by endpoint and status',
    unit: '1',
  }),

  responseTime: meter.createHistogram('api.response.time', {
    description: 'API response time by endpoint',
    unit: 'ms',
  }),
};
