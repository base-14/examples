/**
 * Express 5 + PostgreSQL + OpenTelemetry Application Entry Point
 *
 * CRITICAL: telemetry.ts MUST be imported first to ensure
 * auto-instrumentation captures all dependencies.
 */

import './telemetry.js';

import type { Server } from 'http';
import { createApp } from './app.js';
import { logger } from './logger.js';
import { closeDatabaseConnection, initializeDatabase } from './db/index.js';
import { initializeWebSocket } from './socket.js';

const port = process.env.PORT || 8000;

let server: Server;

async function start() {
  // Initialize database tables
  logger.info('Initializing database...');
  await initializeDatabase();
  logger.info('Database initialized');

  const app = createApp();

  server = app.listen(port, () => {
    logger.info({ port }, 'Server started');
  });

  initializeWebSocket(server);
  logger.info('WebSocket server attached');
}

start().catch((err) => {
  logger.error({ err }, 'Failed to start server');
  process.exit(1);
});

async function gracefulShutdown(signal: string) {
  logger.info({ signal }, 'Received shutdown signal');

  if (server) {
    server.close(async () => {
      logger.info('HTTP server closed');

      await closeDatabaseConnection();
      logger.info('Database connection closed');

      process.exit(0);
    });
  } else {
    process.exit(0);
  }

  // Force shutdown after 30 seconds
  setTimeout(() => {
    logger.error('Could not close connections in time, forcefully shutting down');
    process.exit(1);
  }, 30000);
}

process.on('SIGTERM', () => gracefulShutdown('SIGTERM'));
process.on('SIGINT', () => gracefulShutdown('SIGINT'));
