import { createServer } from 'node:http';
import { createApp } from './app.js';
import { connectDatabase, disconnectDatabase } from './database.js';
import { setupSocketIO } from './socket.js';
import { setSocketIO } from './utils/socketInstance.js';
import { getLogger } from './utils/logger.js';
import { config } from './config.js';
import { redisConnection } from './utils/redis.js';
import { publishQueue } from './jobs/queue.js';
import { articleWorker } from './jobs/workers/articleWorker.js';

const logger = getLogger('server');

async function start(): Promise<void> {
  try {
    await connectDatabase();

    const app = createApp();
    const httpServer = createServer(app);
    const io = setupSocketIO(httpServer);

    app.set('io', io);
    setSocketIO(io);

    httpServer.listen(config.app.port, '0.0.0.0', () => {
      logger.info('Server started', {
        port: config.app.port,
        healthCheck: `http://localhost:${config.app.port}/api/health`,
        websocket: `ws://localhost:${config.app.port}`,
      });
    });

    const gracefulShutdown = async (signal: string): Promise<void> => {
      logger.info('Shutdown signal received', { signal });

      io.close(() => {
        logger.info('Socket.IO server closed');
      });

      httpServer.close(async () => {
        logger.info('HTTP server closed');

        await redisConnection.quit();
        logger.info('Redis connection closed');

        await publishQueue.close();
        await articleWorker.close();
        logger.info('BullMQ closed');

        await disconnectDatabase();

        process.exit(0);
      });

      setTimeout(() => {
        logger.error('Forced shutdown after timeout');
        process.exit(1);
      }, 10000);
    };

    process.on('SIGTERM', () => gracefulShutdown('SIGTERM'));
    process.on('SIGINT', () => gracefulShutdown('SIGINT'));
  } catch (error) {
    logger.error('Failed to start server', error as Error);
    process.exit(1);
  }
}

start();
