import { describe, it, expect, beforeAll, afterAll, beforeEach, afterEach } from 'vitest';
import { io as ioClient, Socket as ClientSocket } from 'socket.io-client';
import { createTestApp, type TestAppInstance } from '../../helpers/app.helper';
import { clearDatabase } from '../../helpers/db.helper';
import { User, type IUser } from '../../../src/models/User';
import { generateToken } from '../../../src/utils/jwt';

describe('Socket.io Integration', () => {
  let testApp: TestAppInstance;
  let testUser: IUser;
  let authToken: string;
  let clientSocket: ClientSocket;
  const TEST_PORT = 3001;

  beforeAll(async () => {
    testApp = createTestApp();

    await new Promise<void>((resolve) => {
      testApp.httpServer.listen(TEST_PORT, () => {
        resolve();
      });
    });
  });

  afterAll(async () => {
    await testApp.close();
  });

  beforeEach(async () => {
    await clearDatabase();

    testUser = await User.create({
      email: 'socketuser@example.com',
      password: 'password123',
      name: 'Socket User',
    });

    authToken = generateToken({
      userId: testUser._id.toString(),
      email: testUser.email,
      role: testUser.role,
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
          token: authToken,
        },
      });

      await new Promise<void>((resolve, reject) => {
        clientSocket.once('connect', () => {
          expect(clientSocket.connected).toBe(true);
          resolve();
        });
        clientSocket.once('connect_error', reject);
      });
    });

    it('should receive connected event with user info', async () => {
      clientSocket = ioClient(`http://localhost:${TEST_PORT}`, {
        auth: {
          token: authToken,
        },
      });

      await new Promise<void>((resolve, reject) => {
        clientSocket.once('connected', (data) => {
          expect(data).toHaveProperty('message');
          expect(data).toHaveProperty('userId', testUser._id.toString());
          resolve();
        });
        clientSocket.once('connect_error', reject);
      });
    });

    it('should reject connection without token', async () => {
      clientSocket = ioClient(`http://localhost:${TEST_PORT}`);

      await new Promise<void>((resolve, reject) => {
        clientSocket.once('connect', () => {
          reject(new Error('Should not connect without token'));
        });
        clientSocket.once('connect_error', (error) => {
          expect(error.message).toMatch(/authentication required/i);
          resolve();
        });
      });
    });

    it('should reject connection with invalid token', async () => {
      clientSocket = ioClient(`http://localhost:${TEST_PORT}`, {
        auth: {
          token: 'invalid.token.here',
        },
      });

      await new Promise<void>((resolve, reject) => {
        clientSocket.once('connect', () => {
          reject(new Error('Should not connect with invalid token'));
        });
        clientSocket.once('connect_error', (error) => {
          expect(error.message).toMatch(/invalid.*token/i);
          resolve();
        });
      });
    });

    it('should support token in Authorization header', async () => {
      clientSocket = ioClient(`http://localhost:${TEST_PORT}`, {
        extraHeaders: {
          Authorization: `Bearer ${authToken}`,
        },
      });

      await new Promise<void>((resolve, reject) => {
        clientSocket.once('connect', () => {
          expect(clientSocket.connected).toBe(true);
          resolve();
        });
        clientSocket.once('connect_error', reject);
      });
    });
  });

  describe('Article Subscriptions', () => {
    beforeEach(async () => {
      clientSocket = ioClient(`http://localhost:${TEST_PORT}`, {
        auth: {
          token: authToken,
        },
      });

      await new Promise<void>((resolve, reject) => {
        clientSocket.once('connect', () => resolve());
        clientSocket.once('connect_error', reject);
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

    it('should receive article events after subscribing', async () => {
      clientSocket.emit('subscribe:articles');

      await new Promise<void>((resolve) => {
        clientSocket.once('subscribed', () => {
          testApp.io.to('articles').emit('article:created', {
            id: 'article-123',
            title: 'New Article',
            authorId: testUser._id.toString(),
            published: false,
            timestamp: new Date(),
          });
        });

        clientSocket.once('article:created', (data) => {
          expect(data).toMatchObject({
            id: 'article-123',
            title: 'New Article',
            authorId: testUser._id.toString(),
          });
          resolve();
        });
      });
    });

    it('should receive multiple event types', async () => {
      const receivedEvents: string[] = [];

      clientSocket.emit('subscribe:articles');

      await new Promise<void>((resolve) => {
        clientSocket.once('subscribed', () => {
          testApp.io.to('articles').emit('article:created', {
            id: 'article-1',
            title: 'Article 1',
          });

          testApp.io.to('articles').emit('article:updated', {
            id: 'article-1',
            title: 'Article 1 Updated',
          });
        });

        clientSocket.once('article:created', () => {
          receivedEvents.push('created');
        });

        clientSocket.once('article:updated', () => {
          receivedEvents.push('updated');
          expect(receivedEvents).toEqual(['created', 'updated']);
          resolve();
        });
      });
    });
  });

  describe('Connection Lifecycle', () => {
    it('should disconnect gracefully', async () => {
      clientSocket = ioClient(`http://localhost:${TEST_PORT}`, {
        auth: {
          token: authToken,
        },
      });

      await new Promise<void>((resolve) => {
        clientSocket.once('connect', () => {
          clientSocket.disconnect();
        });

        clientSocket.once('disconnect', () => {
          expect(clientSocket.connected).toBe(false);
          resolve();
        });
      });
    });

    it('should allow reconnection after disconnect', async () => {
      clientSocket = ioClient(`http://localhost:${TEST_PORT}`, {
        auth: {
          token: authToken,
        },
      });

      await new Promise<void>((resolve) => {
        let connectCount = 0;

        clientSocket.on('connect', () => {
          connectCount++;

          if (connectCount === 1) {
            clientSocket.disconnect();
            setTimeout(() => {
              clientSocket.connect();
            }, 100);
          } else if (connectCount === 2) {
            expect(clientSocket.connected).toBe(true);
            resolve();
          }
        });
      });
    });
  });

  describe('Multiple Clients', () => {
    let secondClient: ClientSocket;
    let secondUser: IUser;
    let secondToken: string;

    beforeEach(async () => {
      secondUser = await User.create({
        email: 'seconduser@example.com',
        password: 'password123',
        name: 'Second User',
      });

      secondToken = generateToken({
        userId: secondUser._id.toString(),
        email: secondUser.email,
        role: secondUser.role,
      });
    });

    afterEach(() => {
      if (secondClient?.connected) {
        secondClient.disconnect();
      }
    });

    it('should support multiple authenticated connections', async () => {
      clientSocket = ioClient(`http://localhost:${TEST_PORT}`, {
        auth: { token: authToken },
      });

      secondClient = ioClient(`http://localhost:${TEST_PORT}`, {
        auth: { token: secondToken },
      });

      await new Promise<void>((resolve) => {
        let connectedCount = 0;

        const checkBothConnected = () => {
          connectedCount++;
          if (connectedCount === 2) {
            expect(clientSocket.connected).toBe(true);
            expect(secondClient.connected).toBe(true);
            resolve();
          }
        };

        clientSocket.once('connect', checkBothConnected);
        secondClient.once('connect', checkBothConnected);
      });
    });

    it('should broadcast events to all subscribed clients', async () => {
      clientSocket = ioClient(`http://localhost:${TEST_PORT}`, {
        auth: { token: authToken },
      });

      secondClient = ioClient(`http://localhost:${TEST_PORT}`, {
        auth: { token: secondToken },
      });

      await new Promise<void>((resolve) => {
        let receivedCount = 0;

        const checkBothReceived = () => {
          receivedCount++;
          if (receivedCount === 2) {
            resolve();
          }
        };

        clientSocket.once('connect', () => {
          clientSocket.emit('subscribe:articles');
        });

        secondClient.once('connect', () => {
          secondClient.emit('subscribe:articles');
        });

        let subscribedCount = 0;
        const checkBothSubscribed = () => {
          subscribedCount++;
          if (subscribedCount === 2) {
            testApp.io.to('articles').emit('article:published', {
              id: 'article-broadcast',
              title: 'Broadcast Article',
            });
          }
        };

        clientSocket.once('subscribed', checkBothSubscribed);
        secondClient.once('subscribed', checkBothSubscribed);

        clientSocket.once('article:published', checkBothReceived);
        secondClient.once('article:published', checkBothReceived);
      });
    });
  });
});
