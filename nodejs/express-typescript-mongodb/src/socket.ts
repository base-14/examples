import type { Server as HTTPServer } from 'http';
import { Server, type Socket } from 'socket.io';
import { trace, SpanStatusCode, context as otelContext } from '@opentelemetry/api';
import { verifyToken } from './utils/jwt.js';
import { User } from './models/User.js';
import { getLogger } from './utils/logger.js';
import { config } from './config.js';

const logger = getLogger('socket');
const tracer = trace.getTracer('socket-io');

export function setupSocketIO(httpServer: HTTPServer): Server {
  const io = new Server(httpServer, {
    cors: {
      origin: config.cors.origin,
      credentials: true,
    },
  });

  io.use(async (socket, next) => {
    const span = tracer.startSpan('socket.authenticate');

    try {
      await otelContext.with(trace.setSpan(otelContext.active(), span), async () => {
        const token =
          socket.handshake.auth.token ?? socket.handshake.headers.authorization?.replace('Bearer ', '');

        if (!token) {
          span.setStatus({ code: SpanStatusCode.ERROR, message: 'No token provided' });
          span.addEvent('auth_failed', { reason: 'missing_token' });
          logger.warn('Socket authentication failed: no token provided', {
            socketId: socket.id,
          });
          return next(new Error('Authentication required'));
        }

        let payload;
        try {
          payload = verifyToken(token);
        } catch {
          span.setStatus({ code: SpanStatusCode.ERROR, message: 'Invalid token' });
          span.addEvent('auth_failed', { reason: 'invalid_token' });
          logger.warn('Socket authentication failed: invalid token', {
            socketId: socket.id,
          });
          return next(new Error('Invalid or expired token'));
        }

        const user = await User.findById(payload.userId);

        if (!user) {
          span.setStatus({ code: SpanStatusCode.ERROR, message: 'User not found' });
          span.addEvent('auth_failed', { reason: 'user_not_found' });
          logger.warn('Socket authentication failed: user not found', {
            socketId: socket.id,
            userId: payload.userId,
          });
          return next(new Error('User not found'));
        }

        socket.data.user = user;

        span.setAttributes({
          'socket.id': socket.id,
          'user.id': user._id.toString(),
          'user.email': user.email,
          'user.role': user.role,
        });

        span.addEvent('auth_success', { 'user.id': user._id.toString() });

        logger.info('Socket authenticated successfully', {
          socketId: socket.id,
          userId: user._id.toString(),
          userEmail: user.email,
        });

        span.setStatus({ code: SpanStatusCode.OK });
        next();
      });
    } catch (error) {
      span.recordException(error as Error);
      span.setStatus({ code: SpanStatusCode.ERROR, message: (error as Error).message });
      logger.error('Socket authentication error', error as Error, {
        socketId: socket.id,
      });
      next(error as Error);
    } finally {
      span.end();
    }
  });

  io.on('connection', (socket: Socket) => {
    const connectionSpan = tracer.startSpan('socket.connection');

    try {
      otelContext.with(trace.setSpan(otelContext.active(), connectionSpan), () => {
        const user = socket.data.user;

        connectionSpan.setAttributes({
          'socket.id': socket.id,
          'user.id': user._id.toString(),
          'user.email': user.email,
        });

        logger.info('Client connected', {
          socketId: socket.id,
          userId: user._id.toString(),
          userEmail: user.email,
        });

        socket.join(`user:${user._id.toString()}`);

        socket.emit('connected', {
          message: 'Connected to article updates',
          userId: user._id.toString(),
        });

        connectionSpan.addEvent('client_connected', {
          'socket.id': socket.id,
          'user.id': user._id.toString(),
        });

        socket.on('subscribe:articles', () => {
          const subscribeSpan = tracer.startSpan('socket.subscribe_articles', {
            attributes: {
              'socket.id': socket.id,
              'user.id': user._id.toString(),
            },
          });

          try {
            socket.join('articles');
            socket.emit('subscribed', { channel: 'articles' });

            logger.info('Client subscribed to articles', {
              socketId: socket.id,
              userId: user._id.toString(),
            });

            subscribeSpan.addEvent('subscribed_to_articles');
            subscribeSpan.setStatus({ code: SpanStatusCode.OK });
          } catch (error) {
            subscribeSpan.recordException(error as Error);
            subscribeSpan.setStatus({ code: SpanStatusCode.ERROR });
            logger.error('Failed to subscribe to articles', error as Error, {
              socketId: socket.id,
              userId: user._id.toString(),
            });
          } finally {
            subscribeSpan.end();
          }
        });

        socket.on('unsubscribe:articles', () => {
          const unsubscribeSpan = tracer.startSpan('socket.unsubscribe_articles', {
            attributes: {
              'socket.id': socket.id,
              'user.id': user._id.toString(),
            },
          });

          try {
            socket.leave('articles');
            socket.emit('unsubscribed', { channel: 'articles' });

            logger.info('Client unsubscribed from articles', {
              socketId: socket.id,
              userId: user._id.toString(),
            });

            unsubscribeSpan.addEvent('unsubscribed_from_articles');
            unsubscribeSpan.setStatus({ code: SpanStatusCode.OK });
          } catch (error) {
            unsubscribeSpan.recordException(error as Error);
            unsubscribeSpan.setStatus({ code: SpanStatusCode.ERROR });
            logger.error('Failed to unsubscribe from articles', error as Error, {
              socketId: socket.id,
              userId: user._id.toString(),
            });
          } finally {
            unsubscribeSpan.end();
          }
        });

        socket.on('disconnect', (reason) => {
          const disconnectSpan = tracer.startSpan('socket.disconnect', {
            attributes: {
              'socket.id': socket.id,
              'user.id': user._id.toString(),
              'disconnect.reason': reason,
            },
          });

          try {
            logger.info('Client disconnected', {
              socketId: socket.id,
              userId: user._id.toString(),
              reason,
            });

            disconnectSpan.addEvent('client_disconnected', { reason });
            disconnectSpan.setStatus({ code: SpanStatusCode.OK });
          } catch (error) {
            disconnectSpan.recordException(error as Error);
            disconnectSpan.setStatus({ code: SpanStatusCode.ERROR });
          } finally {
            disconnectSpan.end();
          }
        });

        connectionSpan.setStatus({ code: SpanStatusCode.OK });
      });
    } catch (error) {
      connectionSpan.recordException(error as Error);
      connectionSpan.setStatus({ code: SpanStatusCode.ERROR });
      logger.error('Connection handler error', error as Error);
    } finally {
      connectionSpan.end();
    }
  });

  return io;
}
