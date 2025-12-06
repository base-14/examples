import { Router } from 'express';
import rateLimit from 'express-rate-limit';
import { register, login, logout, getCurrentUser } from '../controllers/auth.controller.js';
import { authenticate } from '../middleware/auth.middleware.js';
import { validateBody } from '../middleware/validation.middleware.js';
import { registerInputSchema, loginInputSchema } from '../validation/zod-schemas.js';

const router = Router();

const authLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 5,
  standardHeaders: true,
  legacyHeaders: false,
  message: { error: 'Too many authentication attempts, please try again later' },
  skipSuccessfulRequests: false,
  skip: () => process.env.NODE_ENV === 'test',
});

router.post('/register', authLimiter, validateBody(registerInputSchema), register);
router.post('/login', authLimiter, validateBody(loginInputSchema), login);
router.post('/logout', authenticate, logout);
router.get('/me', authenticate, getCurrentUser);

export default router;
