import { createServer, Server as HttpServer } from 'http';
import { Application } from 'express';
import { Server as SocketServer } from 'socket.io';
import { createApp } from '../../src/app';
import { setupSocketIO } from '../../src/socket';

export interface TestAppInstance {
  app: Application;
  httpServer: HttpServer;
  io: SocketServer;
  close: () => Promise<void>;
}

export function createTestApp(): TestAppInstance {
  const app = createApp();
  const httpServer = createServer(app);
  const io = setupSocketIO(httpServer);

  app.set('io', io);

  const close = async (): Promise<void> => {
    return new Promise((resolve) => {
      io.close(() => {
        httpServer.close(() => {
          resolve();
        });
      });
    });
  };

  return {
    app,
    httpServer,
    io,
    close,
  };
}
