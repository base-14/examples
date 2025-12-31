import type { Server as HttpServer } from 'http';
import { Server, type Socket } from 'socket.io';
import { trace, SpanStatusCode, metrics, context, propagation } from '@opentelemetry/api';
import { authService } from './services/auth.js';
import { logger } from './logger.js';
import type { User } from './db/schema.js';

const tracer = trace.getTracer('socket-service');
const meter = metrics.getMeter('socket-service');

const activeConnections = meter.createUpDownCounter('websocket.connections.active', {
  description: 'Number of active WebSocket connections',
  unit: '1',
});

const messagesProcessed = meter.createCounter('websocket.messages.processed', {
  description: 'Total WebSocket messages processed',
  unit: '1',
});

const subscriptionCounter = meter.createCounter('websocket.subscriptions.total', {
  description: 'Total channel subscriptions',
  unit: '1',
});

interface AuthenticatedSocket extends Socket {
  user?: User;
}

let io: Server | null = null;

export function initializeWebSocket(httpServer: HttpServer): Server {
  io = new Server(httpServer, {
    cors: {
      origin: process.env.CORS_ORIGIN || '*',
      methods: ['GET', 'POST'],
    },
    transports: ['websocket', 'polling'],
  });

  io.use(async (socket: AuthenticatedSocket, next) => {
    return tracer.startActiveSpan('socket.authenticate', async (span) => {
      try {
        span.setAttribute('socket.id', socket.id);

        const token =
          socket.handshake.auth?.token ||
          socket.handshake.headers?.authorization?.replace('Bearer ', '');

        if (!token) {
          span.setStatus({ code: SpanStatusCode.ERROR, message: 'No token provided' });
          span.end();
          return next(new Error('Authentication required'));
        }

        const payload = authService.verifyToken(token);
        const user = await authService.getUserById(payload.userId);

        if (!user) {
          span.setStatus({ code: SpanStatusCode.ERROR, message: 'User not found' });
          span.end();
          return next(new Error('User not found'));
        }

        socket.user = user;
        span.setAttribute('user.id', user.id);
        span.setStatus({ code: SpanStatusCode.OK });
        span.end();

        logger.info({ socketId: socket.id, userId: user.id }, 'Socket authenticated');
        next();
      } catch (error) {
        span.recordException(error as Error);
        span.setStatus({ code: SpanStatusCode.ERROR, message: 'Authentication failed' });
        span.end();
        next(new Error('Invalid token'));
      }
    });
  });

  io.on('connection', (socket: AuthenticatedSocket) => {
    tracer.startActiveSpan('socket.connection', (span) => {
      span.setAttribute('socket.id', socket.id);
      if (socket.user) {
        span.setAttribute('user.id', socket.user.id);
      }

      activeConnections.add(1, { authenticated: socket.user ? 'true' : 'false' });

      logger.info(
        { socketId: socket.id, userId: socket.user?.id },
        'Client connected'
      );

      socket.on('subscribe', (channel: string) => {
        tracer.startActiveSpan(`socket.subscribe_${channel}`, (subscribeSpan) => {
          subscribeSpan.setAttribute('socket.id', socket.id);
          subscribeSpan.setAttribute('channel', channel);
          if (socket.user) {
            subscribeSpan.setAttribute('user.id', socket.user.id);
          }

          const allowedChannels = ['articles', 'notifications'];
          if (!allowedChannels.includes(channel)) {
            subscribeSpan.setStatus({ code: SpanStatusCode.ERROR, message: 'Invalid channel' });
            subscribeSpan.end();
            socket.emit('error', { message: `Invalid channel: ${channel}` });
            return;
          }

          socket.join(channel);
          subscriptionCounter.add(1, { channel });

          logger.info(
            { socketId: socket.id, userId: socket.user?.id, channel },
            'Client subscribed to channel'
          );

          subscribeSpan.setStatus({ code: SpanStatusCode.OK });
          subscribeSpan.end();

          socket.emit('subscribed', { channel });
        });
      });

      socket.on('unsubscribe', (channel: string) => {
        tracer.startActiveSpan('socket.unsubscribe', (unsubscribeSpan) => {
          unsubscribeSpan.setAttribute('socket.id', socket.id);
          unsubscribeSpan.setAttribute('channel', channel);
          if (socket.user) {
            unsubscribeSpan.setAttribute('user.id', socket.user.id);
          }

          socket.leave(channel);

          logger.info(
            { socketId: socket.id, userId: socket.user?.id, channel },
            'Client unsubscribed from channel'
          );

          unsubscribeSpan.setStatus({ code: SpanStatusCode.OK });
          unsubscribeSpan.end();

          socket.emit('unsubscribed', { channel });
        });
      });

      socket.on('message', (data: { channel: string; content: unknown }) => {
        tracer.startActiveSpan('socket.message', (messageSpan) => {
          messageSpan.setAttribute('socket.id', socket.id);
          messageSpan.setAttribute('channel', data.channel);
          if (socket.user) {
            messageSpan.setAttribute('user.id', socket.user.id);
          }

          messagesProcessed.add(1, { channel: data.channel, direction: 'inbound' });

          logger.debug(
            { socketId: socket.id, userId: socket.user?.id, channel: data.channel },
            'Message received'
          );

          messageSpan.setStatus({ code: SpanStatusCode.OK });
          messageSpan.end();
        });
      });

      socket.on('disconnect', (reason: string) => {
        tracer.startActiveSpan('socket.disconnect', (disconnectSpan) => {
          disconnectSpan.setAttribute('socket.id', socket.id);
          disconnectSpan.setAttribute('disconnect.reason', reason);
          if (socket.user) {
            disconnectSpan.setAttribute('user.id', socket.user.id);
          }

          activeConnections.add(-1, { authenticated: socket.user ? 'true' : 'false' });

          logger.info(
            { socketId: socket.id, userId: socket.user?.id, reason },
            'Client disconnected'
          );

          disconnectSpan.setStatus({ code: SpanStatusCode.OK });
          disconnectSpan.end();
        });
      });

      span.setStatus({ code: SpanStatusCode.OK });
      span.end();
    });
  });

  logger.info('WebSocket server initialized');
  return io;
}

export function getIO(): Server | null {
  return io;
}

export function broadcastToChannel(
  channel: string,
  event: string,
  data: Record<string, unknown>,
  traceContext?: Record<string, string>
): void {
  if (!io) {
    logger.warn('WebSocket server not initialized, cannot broadcast');
    return;
  }

  tracer.startActiveSpan('socket.broadcast', (span) => {
    span.setAttribute('channel', channel);
    span.setAttribute('event', event);

    if (traceContext) {
      const ctx = propagation.extract(context.active(), traceContext);
      context.with(ctx, () => {
        span.setAttribute('trace.parent_id', traceContext['traceparent'] || 'unknown');
      });
    }

    io!.to(channel).emit(event, {
      ...data,
      timestamp: new Date().toISOString(),
    });

    messagesProcessed.add(1, { channel, direction: 'outbound', event });

    logger.debug({ channel, event }, 'Broadcast message sent');

    span.setStatus({ code: SpanStatusCode.OK });
    span.end();
  });
}
