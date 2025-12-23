/* eslint-disable @typescript-eslint/no-unsafe-member-access */
import { io as ioClient, Socket as ClientSocket } from 'socket.io-client';
import {
  createTestApp,
  closeTestApp,
  TestAppInstance,
} from '../helpers/test-app.helper';
import { clearDatabase } from '../helpers/db.helper';
import { createTestUser, TestUser } from '../helpers/auth.helper';

describe('WebSocket (e2e)', () => {
  let testApp: TestAppInstance;
  let testUser: TestUser;
  let clientSocket: ClientSocket;
  const TEST_PORT = 3002;

  beforeAll(async () => {
    testApp = await createTestApp();
    await testApp.app.listen(TEST_PORT);
  });

  afterAll(async () => {
    await closeTestApp(testApp);
  });

  beforeEach(async () => {
    await clearDatabase(testApp.app);
    testUser = await createTestUser(testApp.app, {
      email: 'socketuser@example.com',
      password: 'Password123',
      name: 'Socket User',
    });

    if (clientSocket?.connected) {
      clientSocket.disconnect();
    }
  });

  afterEach(() => {
    if (clientSocket?.connected) {
      clientSocket.disconnect();
    }
  });

  describe('Authentication', () => {
    it('should connect successfully with valid token', async () => {
      clientSocket = ioClient(`http://localhost:${TEST_PORT}`, {
        auth: {
          token: testUser.token,
        },
      });

      await new Promise<void>((resolve, reject) => {
        const timeout = setTimeout(
          () => reject(new Error('Connection timeout')),
          5000,
        );
        clientSocket.once('connect', () => {
          clearTimeout(timeout);
          expect(clientSocket.connected).toBe(true);
          resolve();
        });
        clientSocket.once('connect_error', (error) => {
          clearTimeout(timeout);
          reject(error);
        });
      });
    });

    it('should receive connected event with user info', async () => {
      clientSocket = ioClient(`http://localhost:${TEST_PORT}`, {
        auth: {
          token: testUser.token,
        },
      });

      await new Promise<void>((resolve, reject) => {
        const timeout = setTimeout(
          () => reject(new Error('Connection timeout')),
          5000,
        );
        clientSocket.once('connected', (data) => {
          clearTimeout(timeout);
          expect(data).toHaveProperty('message');
          expect(data).toHaveProperty('userId', testUser.id);
          resolve();
        });
        clientSocket.once('connect_error', (error) => {
          clearTimeout(timeout);
          reject(error);
        });
      });
    });

    it('should disconnect without token', async () => {
      clientSocket = ioClient(`http://localhost:${TEST_PORT}`);

      await new Promise<void>((resolve) => {
        const timeout = setTimeout(() => {
          expect(clientSocket.connected).toBe(false);
          resolve();
        }, 2000);

        clientSocket.once('error', () => {
          clearTimeout(timeout);
          resolve();
        });

        clientSocket.once('disconnect', () => {
          clearTimeout(timeout);
          resolve();
        });
      });
    });

    it('should disconnect with invalid token', async () => {
      clientSocket = ioClient(`http://localhost:${TEST_PORT}`, {
        auth: {
          token: 'invalid.token.here',
        },
      });

      await new Promise<void>((resolve) => {
        const timeout = setTimeout(() => {
          expect(clientSocket.connected).toBe(false);
          resolve();
        }, 2000);

        clientSocket.once('error', () => {
          clearTimeout(timeout);
          resolve();
        });

        clientSocket.once('disconnect', () => {
          clearTimeout(timeout);
          resolve();
        });
      });
    });
  });

  describe('Article Subscriptions', () => {
    beforeEach(async () => {
      clientSocket = ioClient(`http://localhost:${TEST_PORT}`, {
        auth: {
          token: testUser.token,
        },
      });

      await new Promise<void>((resolve, reject) => {
        const timeout = setTimeout(
          () => reject(new Error('Connection timeout')),
          5000,
        );
        clientSocket.once('connect', () => {
          clearTimeout(timeout);
          resolve();
        });
        clientSocket.once('connect_error', (error) => {
          clearTimeout(timeout);
          reject(error);
        });
      });
    });

    it('should subscribe to articles channel', async () => {
      clientSocket.emit('subscribe:articles');

      await new Promise<void>((resolve) => {
        clientSocket.once('subscribed', (data) => {
          expect(data.channel).toBe('articles');
          resolve();
        });
      });
    });

    it('should unsubscribe from articles channel', async () => {
      clientSocket.emit('subscribe:articles');

      await new Promise<void>((resolve) => {
        clientSocket.once('subscribed', () => {
          clientSocket.emit('unsubscribe:articles');

          clientSocket.once('unsubscribed', (data) => {
            expect(data.channel).toBe('articles');
            resolve();
          });
        });
      });
    });
  });

  describe('Connection Lifecycle', () => {
    it('should disconnect gracefully', async () => {
      clientSocket = ioClient(`http://localhost:${TEST_PORT}`, {
        auth: {
          token: testUser.token,
        },
      });

      await new Promise<void>((resolve, reject) => {
        const timeout = setTimeout(() => reject(new Error('Timeout')), 5000);
        clientSocket.once('connect', () => {
          clearTimeout(timeout);
          clientSocket.disconnect();
        });
        clientSocket.once('connect_error', (error) => {
          clearTimeout(timeout);
          reject(error);
        });
        clientSocket.once('disconnect', () => {
          expect(clientSocket.connected).toBe(false);
          resolve();
        });
      });
    });
  });
});
