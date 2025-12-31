import type { Request, Response, NextFunction } from 'express';
import { authService } from '../services/auth.js';

export async function requireAuth(req: Request, res: Response, next: NextFunction) {
  const authHeader = req.headers.authorization;

  if (!authHeader?.startsWith('Bearer ')) {
    res.status(401).json({ error: 'Authorization header required' });
    return;
  }

  const token = authHeader.slice(7);

  try {
    const payload = authService.verifyToken(token);
    const user = await authService.getUserById(payload.userId);

    if (!user) {
      res.status(401).json({ error: 'User not found' });
      return;
    }

    req.user = user;
    next();
  } catch {
    res.status(401).json({ error: 'Invalid or expired token' });
  }
}

export async function optionalAuth(req: Request, res: Response, next: NextFunction) {
  const authHeader = req.headers.authorization;

  if (!authHeader?.startsWith('Bearer ')) {
    next();
    return;
  }

  const token = authHeader.slice(7);

  try {
    const payload = authService.verifyToken(token);
    const user = await authService.getUserById(payload.userId);
    if (user) {
      req.user = user;
    }
  } catch {
    // Ignore invalid tokens for optional auth
  }

  next();
}
