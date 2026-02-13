import { Hono } from 'hono';
import { zValidator } from '@hono/zod-validator';
import * as userService from '../services/user.js';
import { registerSchema, loginSchema, updateUserSchema } from '../validators/user.js';
import { authenticate } from '../middleware/auth.js';
import { createLogger } from '../services/logger.js';
import type { Variables } from '../types/index.js';

const logger = createLogger('auth-routes');
const authRouter = new Hono<{ Variables: Variables }>();

authRouter.post('/register', zValidator('json', registerSchema), async (c) => {
  try {
    const data = c.req.valid('json');
    const user = await userService.createUser(data);
    const token = userService.generateToken(user);

    return c.json({ user, token }, 201);
  } catch (error) {
    if ((error as Error).message === 'Email already exists') {
      logger.warn({ email: c.req.valid('json').email }, 'Registration failed: email already exists');
      return c.json({ error: 'Conflict', message: 'Email already exists' }, 409);
    }
    throw error;
  }
});

authRouter.post('/login', zValidator('json', loginSchema), async (c) => {
  try {
    const { email, password } = c.req.valid('json');
    const user = await userService.validateCredentials(email, password);
    const token = userService.generateToken(user);

    return c.json({ user, token });
  } catch (error) {
    if ((error as Error).message === 'Invalid credentials') {
      logger.warn({ email: c.req.valid('json').email }, 'Login failed: invalid credentials');
      return c.json({ error: 'Unauthorized', message: 'Invalid email or password' }, 401);
    }
    throw error;
  }
});

authRouter.get('/user', authenticate, async (c) => {
  const { id } = c.get('user');
  const user = await userService.findById(id);

  if (!user) {
    return c.json({ error: 'Not Found', message: 'User not found' }, 404);
  }

  return c.json({ user });
});

authRouter.put('/user', authenticate, zValidator('json', updateUserSchema), async (c) => {
  const { id } = c.get('user');
  const updates = c.req.valid('json');
  const user = await userService.updateUser(id, updates);

  if (!user) {
    return c.json({ error: 'Not Found', message: 'User not found' }, 404);
  }

  return c.json({ user });
});

authRouter.post('/logout', authenticate, async (c) => {
  return c.json({ message: 'Logged out successfully' });
});

export default authRouter;
