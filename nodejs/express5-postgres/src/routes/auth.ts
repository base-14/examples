import { Router } from 'express';
import { z } from 'zod';
import { trace } from '@opentelemetry/api';
import { authService } from '../services/auth.js';
import { requireAuth } from '../middleware/auth.js';

const router = Router();

const registerSchema = z.object({
  email: z.string().email(),
  password: z.string().min(8),
  name: z.string().min(1).max(255),
});

const loginSchema = z.object({
  email: z.string().email(),
  password: z.string().min(1),
});

function formatUserResponse(user: { id: number; email: string; name: string; bio?: string | null; image?: string | null }) {
  return {
    id: user.id,
    email: user.email,
    name: user.name,
    bio: user.bio || null,
    image: user.image || null,
  };
}

function errorResponse(message: string, statusCode: number, res: Express.Response) {
  const span = trace.getActiveSpan();
  const spanContext = span?.spanContext();

  const response: Record<string, unknown> = { error: message };
  if (spanContext?.traceId) {
    response.trace_id = spanContext.traceId;
  }

  // @ts-expect-error - Express response type
  return res.status(statusCode).json(response);
}

router.post('/register', async (req, res) => {
  const result = registerSchema.safeParse(req.body);

  if (!result.success) {
    return errorResponse(result.error.issues[0]?.message || 'Validation failed', 400, res);
  }

  try {
    const { user, token } = await authService.register(
      result.data.email,
      result.data.password,
      result.data.name
    );

    res.status(201).json({
      user: formatUserResponse(user),
      token,
    });
  } catch (error) {
    const err = error as Error & { statusCode?: number };
    return errorResponse(err.message, err.statusCode || 500, res);
  }
});

router.post('/login', async (req, res) => {
  const result = loginSchema.safeParse(req.body);

  if (!result.success) {
    return errorResponse(result.error.issues[0]?.message || 'Validation failed', 400, res);
  }

  try {
    const { user, token } = await authService.login(result.data.email, result.data.password);

    res.json({
      user: formatUserResponse(user),
      token,
    });
  } catch (error) {
    const err = error as Error & { statusCode?: number };
    return errorResponse(err.message, err.statusCode || 500, res);
  }
});

router.get('/user', requireAuth, (req, res) => {
  if (!req.user) {
    return errorResponse('User not found', 404, res);
  }

  res.json({
    user: formatUserResponse(req.user),
  });
});

router.post('/logout', requireAuth, (req, res) => {
  // Stateless JWT - just acknowledge the logout
  res.json({ message: 'Logged out successfully' });
});

export { router as authRouter };
