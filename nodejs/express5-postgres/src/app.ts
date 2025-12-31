import express from 'express';
import { router } from './routes/index.js';
import { errorHandler, notFoundHandler } from './middleware/error.js';
import { metricsMiddleware } from './middleware/metrics.js';

export function createApp() {
  const app = express();

  // Middleware
  app.use(express.json({ limit: '10kb' }));
  app.use(metricsMiddleware);

  // Routes
  app.use(router);

  // Error handling
  app.use(notFoundHandler);
  app.use(errorHandler);

  return app;
}
