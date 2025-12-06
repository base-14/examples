import type { Request, Response, NextFunction } from 'express';
import { trace, SpanStatusCode } from '@opentelemetry/api';
import { verifyToken } from '../utils/jwt.js';
import { User } from '../models/User.js';
import { getLogger } from '../utils/logger.js';

const logger = getLogger('auth-middleware');

export async function authenticate(
  req: Request,
  res: Response,
  next: NextFunction
): Promise<void> {
  const currentSpan = trace.getActiveSpan();

  try {
    const authHeader = req.headers.authorization;

    if (!authHeader?.startsWith('Bearer ')) {
      if (currentSpan) {
        currentSpan.addEvent('auth_failed', { reason: 'missing_token' });
      }
      logger.warn('Authentication failed - missing token', {
        path: req.path,
        method: req.method,
        ip: req.ip,
        reason: 'missing_token',
      });
      res.status(401).json({ error: 'Authentication required' });
      return;
    }

    const token = authHeader.substring(7);

    let payload;
    try {
      payload = verifyToken(token);
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      if (currentSpan) {
        currentSpan.addEvent('auth_failed', { reason: 'invalid_token' });
      }
      logger.warn('Authentication failed - invalid or expired token', {
        path: req.path,
        method: req.method,
        ip: req.ip,
        reason: 'invalid_token',
        error: errorMessage,
      });
      res.status(401).json({ error: 'Invalid or expired token' });
      return;
    }

    const user = await User.findById(payload.userId);

    if (!user) {
      if (currentSpan) {
        currentSpan.addEvent('auth_failed', { reason: 'user_not_found' });
      }
      logger.warn('Authentication failed - user not found', {
        path: req.path,
        method: req.method,
        ip: req.ip,
        reason: 'user_not_found',
        userId: payload.userId,
      });
      res.status(401).json({ error: 'User not found' });
      return;
    }

    req.user = user;

    if (currentSpan) {
      currentSpan.setAttributes({
        'user.id': user._id.toString(),
        'user.email': user.email,
        'user.role': user.role,
      });
    }

    next();
  } catch (error) {
    if (currentSpan) {
      currentSpan.recordException(error as Error);
      currentSpan.setStatus({ code: SpanStatusCode.ERROR, message: (error as Error).message });
    }
    next(error);
  }
}
