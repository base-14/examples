import { getMeter } from './telemetry';

const meter = getMeter('api');

export const httpRequestCounter = meter.createCounter('http.server.requests', {
  description: 'Total number of HTTP requests',
  unit: '1',
});

export const httpRequestDuration = meter.createHistogram('http.server.duration', {
  description: 'HTTP request duration in milliseconds',
  unit: 'ms',
});

export const httpErrorCounter = meter.createCounter('http.server.errors', {
  description: 'Total number of HTTP errors',
  unit: '1',
});

export const authCounter = meter.createCounter('auth.operations', {
  description: 'Authentication operations count',
  unit: '1',
});

export const articleCounter = meter.createCounter('articles.operations', {
  description: 'Article operations count',
  unit: '1',
});

export const favoriteCounter = meter.createCounter('favorites.operations', {
  description: 'Favorite operations count',
  unit: '1',
});

export const commentCounter = meter.createCounter('comments.operations', {
  description: 'Comment operations count',
  unit: '1',
});

export const dbOperationDuration = meter.createHistogram('db.operation.duration', {
  description: 'Database operation duration in milliseconds',
  unit: 'ms',
});

export function recordRequest(
  method: string,
  route: string,
  statusCode: number,
  durationMs: number
): void {
  const attributes = {
    'http.method': method,
    'http.route': route,
    'http.status_code': statusCode,
  };

  httpRequestCounter.add(1, attributes);
  httpRequestDuration.record(durationMs, attributes);

  if (statusCode >= 400) {
    httpErrorCounter.add(1, {
      ...attributes,
      'error.type': statusCode >= 500 ? 'server' : 'client',
    });
  }
}

export function recordAuth(operation: 'register' | 'login', success: boolean): void {
  authCounter.add(1, {
    operation,
    success: String(success),
  });
}

export function recordArticle(
  operation: 'create' | 'update' | 'delete' | 'view' | 'list',
  success: boolean
): void {
  articleCounter.add(1, {
    operation,
    success: String(success),
  });
}

export function recordFavorite(operation: 'favorite' | 'unfavorite', success: boolean): void {
  favoriteCounter.add(1, {
    operation,
    success: String(success),
  });
}

export function recordComment(
  operation: 'list' | 'create' | 'delete',
  success: boolean
): void {
  commentCounter.add(1, {
    operation,
    success: String(success),
  });
}

export function recordDbOperation(operation: string, durationMs: number): void {
  dbOperationDuration.record(durationMs, {
    'db.operation': operation,
  });
}
