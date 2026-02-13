import { Context, Next } from 'hono';
import jwt from 'jsonwebtoken';
import { config } from '../config/index.js';
import { createLogger } from '../services/logger.js';
import type { JwtPayload } from '../types/index.js';

const logger = createLogger('auth-middleware');

export async function authenticate(c: Context, next: Next) {
  const authHeader = c.req.header('Authorization');

  if (!authHeader || !authHeader.startsWith('Bearer ')) {
    logger.warn({ path: c.req.path, method: c.req.method }, 'Auth failed: missing or invalid token');
    return c.json({ error: 'Unauthorized', message: 'Missing or invalid token' }, 401);
  }

  const token = authHeader.slice(7);

  try {
    const payload = jwt.verify(token, config.jwt.secret) as JwtPayload;
    c.set('user', payload);
    await next();
  } catch {
    logger.warn({ path: c.req.path, method: c.req.method }, 'Auth failed: invalid or expired token');
    return c.json({ error: 'Unauthorized', message: 'Invalid or expired token' }, 401);
  }
}

export function optionalAuth(c: Context, next: Next) {
  const authHeader = c.req.header('Authorization');

  if (authHeader?.startsWith('Bearer ')) {
    const token = authHeader.slice(7);
    try {
      const payload = jwt.verify(token, config.jwt.secret) as JwtPayload;
      c.set('user', payload);
    } catch {
      // Token invalid, continue without user
    }
  }

  return next();
}
