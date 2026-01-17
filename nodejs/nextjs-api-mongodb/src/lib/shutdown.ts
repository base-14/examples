import mongoose from 'mongoose';
import { emailQueue, analyticsQueue } from './queue';
import { logger } from './logger';

const SHUTDOWN_TIMEOUT_MS = 30000;

let isShuttingDown = false;

async function closeMongoose(): Promise<void> {
  try {
    if (mongoose.connection.readyState !== 0) {
      await mongoose.connection.close();
      logger.info('MongoDB connection closed');
    }
  } catch (error) {
    logger.error('Error closing MongoDB connection', {
      errorMessage: error instanceof Error ? error.message : 'Unknown error',
    });
  }
}

async function closeQueues(): Promise<void> {
  try {
    await Promise.all([emailQueue.close(), analyticsQueue.close()]);
    logger.info('BullMQ queues closed');
  } catch (error) {
    logger.error('Error closing BullMQ queues', {
      errorMessage: error instanceof Error ? error.message : 'Unknown error',
    });
  }
}

export async function gracefulShutdown(signal: string): Promise<void> {
  if (isShuttingDown) {
    logger.warn('Shutdown already in progress');
    return;
  }

  isShuttingDown = true;
  logger.info('Graceful shutdown initiated', { signal });

  const shutdownTimer = setTimeout(() => {
    logger.error('Shutdown timeout reached, forcing exit');
    process.exit(1);
  }, SHUTDOWN_TIMEOUT_MS);

  try {
    await Promise.all([closeMongoose(), closeQueues()]);

    logger.info('Graceful shutdown completed');
    clearTimeout(shutdownTimer);
  } catch (error) {
    logger.error('Error during graceful shutdown', {
      errorMessage: error instanceof Error ? error.message : 'Unknown error',
    });
    clearTimeout(shutdownTimer);
  }
}

export function registerShutdownHandlers(): void {
  process.on('SIGTERM', () => gracefulShutdown('SIGTERM'));
  process.on('SIGINT', () => gracefulShutdown('SIGINT'));

  process.on('uncaughtException', (error) => {
    logger.error('Uncaught exception', {
      errorName: error.name,
      errorMessage: error.message,
      stack: error.stack,
    });
    gracefulShutdown('uncaughtException').finally(() => process.exit(1));
  });

  process.on('unhandledRejection', (reason) => {
    logger.error('Unhandled rejection', {
      reason: reason instanceof Error ? reason.message : String(reason),
    });
  });

  logger.info('Shutdown handlers registered');
}
