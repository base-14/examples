import {
  WebSocketGateway,
  WebSocketServer,
  SubscribeMessage,
  OnGatewayConnection,
  OnGatewayDisconnect,
  ConnectedSocket,
  WsException,
} from '@nestjs/websockets';
import { Server, Socket } from 'socket.io';
import { JwtService } from '@nestjs/jwt';
import { ConfigService } from '@nestjs/config';
import {
  trace,
  SpanStatusCode,
  context as otelContext,
} from '@opentelemetry/api';
import { UsersService } from '../users/users.service';
import { User } from '../users/entities/user.entity';
import { BusinessMetrics } from '../common/metrics/business.metrics';

interface JwtPayload {
  sub: string;
  email: string;
}

interface SocketData {
  user?: User;
}

const tracer = trace.getTracer('events-gateway');

export interface ArticleEvent {
  id: string;
  title: string;
  authorId: string;
  published?: boolean;
  timestamp: Date;
}

@WebSocketGateway({
  cors: {
    origin: '*',
    credentials: true,
  },
})
export class EventsGateway implements OnGatewayConnection, OnGatewayDisconnect {
  @WebSocketServer()
  server: Server;

  constructor(
    private jwtService: JwtService,
    private configService: ConfigService,
    private usersService: UsersService,
  ) {}

  async handleConnection(client: Socket) {
    const span = tracer.startSpan('socket.authenticate');

    try {
      await otelContext.with(
        trace.setSpan(otelContext.active(), span),
        async () => {
          const token =
            (client.handshake.auth as { token?: string }).token ||
            client.handshake.headers.authorization?.replace('Bearer ', '');

          if (!token) {
            span.setStatus({
              code: SpanStatusCode.ERROR,
              message: 'No token provided',
            });
            span.addEvent('auth_failed', { reason: 'missing_token' });
            client.emit('error', { message: 'Authentication required' });
            client.disconnect();
            return;
          }

          try {
            const payload = this.jwtService.verify<JwtPayload>(token, {
              secret: this.configService.get<string>('jwt.secret'),
            });

            const user = await this.usersService.findById(payload.sub);

            if (!user) {
              span.setStatus({
                code: SpanStatusCode.ERROR,
                message: 'User not found',
              });
              span.addEvent('auth_failed', { reason: 'user_not_found' });
              client.emit('error', { message: 'User not found' });
              client.disconnect();
              return;
            }

            (client.data as SocketData).user = user;
            client.join(`user:${user.id}`);

            span.setAttributes({
              'socket.id': client.id,
              'user.id': user.id,
              'user.email': user.email,
            });

            span.addEvent('auth_success', { 'user.id': user.id });

            client.emit('connected', {
              message: 'Connected to article updates',
              userId: user.id,
            });

            BusinessMetrics.websocketConnections.add(1);
            span.setStatus({ code: SpanStatusCode.OK });
          } catch {
            span.setStatus({
              code: SpanStatusCode.ERROR,
              message: 'Invalid token',
            });
            span.addEvent('auth_failed', { reason: 'invalid_token' });
            client.emit('error', { message: 'Invalid or expired token' });
            client.disconnect();
          }
        },
      );
    } catch (error) {
      span.recordException(error as Error);
      span.setStatus({
        code: SpanStatusCode.ERROR,
        message: (error as Error).message,
      });
      client.disconnect();
    } finally {
      span.end();
    }
  }

  handleDisconnect(client: Socket) {
    const socketData = client.data as SocketData;
    const span = tracer.startSpan('socket.disconnect', {
      attributes: {
        'socket.id': client.id,
        'user.id': socketData.user?.id,
      },
    });

    try {
      if (socketData.user) {
        BusinessMetrics.websocketConnections.add(-1);
      }
      span.addEvent('client_disconnected');
      span.setStatus({ code: SpanStatusCode.OK });
    } finally {
      span.end();
    }
  }

  @SubscribeMessage('subscribe:articles')
  handleSubscribeArticles(@ConnectedSocket() client: Socket) {
    const socketData = client.data as SocketData;
    const span = tracer.startSpan('socket.subscribe_articles', {
      attributes: {
        'socket.id': client.id,
        'user.id': socketData.user?.id,
      },
    });

    try {
      if (!socketData.user) {
        throw new WsException('Not authenticated');
      }

      client.join('articles');
      span.addEvent('subscribed_to_articles');
      span.setStatus({ code: SpanStatusCode.OK });

      return { event: 'subscribed', data: { channel: 'articles' } };
    } catch (error) {
      span.recordException(error as Error);
      span.setStatus({ code: SpanStatusCode.ERROR });
      throw error;
    } finally {
      span.end();
    }
  }

  @SubscribeMessage('unsubscribe:articles')
  handleUnsubscribeArticles(@ConnectedSocket() client: Socket) {
    const socketData = client.data as SocketData;
    const span = tracer.startSpan('socket.unsubscribe_articles', {
      attributes: {
        'socket.id': client.id,
        'user.id': socketData.user?.id,
      },
    });

    try {
      client.leave('articles');
      span.addEvent('unsubscribed_from_articles');
      span.setStatus({ code: SpanStatusCode.OK });

      return { event: 'unsubscribed', data: { channel: 'articles' } };
    } finally {
      span.end();
    }
  }

  emitArticleCreated(event: ArticleEvent) {
    const span = tracer.startSpan('websocket.emit', {
      attributes: {
        'websocket.event': 'article:created',
        'article.id': event.id,
        room: 'articles',
      },
    });
    try {
      this.server.to('articles').emit('article:created', event);
      BusinessMetrics.websocketEvents.add(1, { event_type: 'article:created' });
      span.setStatus({ code: SpanStatusCode.OK });
    } finally {
      span.end();
    }
  }

  emitArticleUpdated(event: ArticleEvent) {
    const span = tracer.startSpan('websocket.emit', {
      attributes: {
        'websocket.event': 'article:updated',
        'article.id': event.id,
        room: 'articles',
      },
    });
    try {
      this.server.to('articles').emit('article:updated', event);
      BusinessMetrics.websocketEvents.add(1, { event_type: 'article:updated' });
      span.setStatus({ code: SpanStatusCode.OK });
    } finally {
      span.end();
    }
  }

  emitArticleDeleted(event: Omit<ArticleEvent, 'published'>) {
    const span = tracer.startSpan('websocket.emit', {
      attributes: {
        'websocket.event': 'article:deleted',
        'article.id': event.id,
        room: 'articles',
      },
    });
    try {
      this.server.to('articles').emit('article:deleted', event);
      BusinessMetrics.websocketEvents.add(1, { event_type: 'article:deleted' });
      span.setStatus({ code: SpanStatusCode.OK });
    } finally {
      span.end();
    }
  }

  emitArticlePublished(event: ArticleEvent) {
    const span = tracer.startSpan('websocket.emit', {
      attributes: {
        'websocket.event': 'article:published',
        'article.id': event.id,
        room: 'articles',
      },
    });
    try {
      this.server.to('articles').emit('article:published', event);
      BusinessMetrics.websocketEvents.add(1, {
        event_type: 'article:published',
      });
      span.setStatus({ code: SpanStatusCode.OK });
    } finally {
      span.end();
    }
  }
}
