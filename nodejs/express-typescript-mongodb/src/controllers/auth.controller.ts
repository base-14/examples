import type { Request, Response, NextFunction } from 'express';
import { User } from '../models/User.js';
import { generateToken } from '../utils/jwt.js';
import { authMetrics } from '../utils/metrics.js';
import { getLogger } from '../utils/logger.js';
import { withSpan, setSpanError } from '../utils/tracing.js';
import {
  AuthenticationError,
  ConflictError,
} from '../utils/errors.js';

const TRACER_NAME = 'auth-controller';
const logger = getLogger('auth-controller');

export async function register(
  req: Request,
  res: Response,
  next: NextFunction
): Promise<void> {
  try {
    await withSpan(TRACER_NAME, 'auth.register', async (span) => {
      const { email, password, name } = req.body;

      const existingUser = await User.findOne({ email });
      if (existingUser) {
        setSpanError(span, 'Email already exists');
        throw new ConflictError('Email already exists');
      }

      const user = await User.create({
        email,
        password,
        name,
        role: 'user',
      });

      logger.info('User registered successfully', {
        'user.id': user._id.toString(),
        'user.email': email,
        'user.role': user.role,
      });

      const token = generateToken({
        userId: user._id.toString(),
        email: user.email,
        role: user.role,
      });

      authMetrics.registrations.add(1, { 'user.role': user.role });
      authMetrics.activeUsers.add(1);

      span.setAttributes({
        'user.id': user._id.toString(),
        'user.email': user.email,
        'user.role': user.role,
      });

      span.addEvent('user_registered', {
        'user.id': user._id.toString(),
        'user.email': user.email,
      });

      res.status(201).json({
        token,
        user: {
          id: user._id,
          email: user.email,
          name: user.name,
          role: user.role,
        },
      });
    });
  } catch (error) {
    next(error);
  }
}

export async function login(
  req: Request,
  res: Response,
  next: NextFunction
): Promise<void> {
  try {
    await withSpan(TRACER_NAME, 'auth.login', async (span) => {
      const { email, password } = req.body;

      const user = await User.findOne({ email });
      if (!user) {
        logger.warn('Login failed - user not found', {
          'user.email': email,
          reason: 'user_not_found',
        });
        authMetrics.loginFailed.add(1, { reason: 'user_not_found' });
        span.addEvent('login_failed', { reason: 'user_not_found' });
        setSpanError(span, 'Invalid credentials');
        throw new AuthenticationError('Invalid credentials');
      }

      const isPasswordValid = await user.comparePassword(password);
      if (!isPasswordValid) {
        logger.warn('Login failed - invalid password', {
          'user.id': user._id.toString(),
          'user.email': email,
          reason: 'invalid_password',
        });
        authMetrics.loginFailed.add(1, {
          reason: 'invalid_password',
          'user.id': user._id.toString(),
        });
        span.addEvent('login_failed', {
          'user.id': user._id.toString(),
          reason: 'invalid_password',
        });
        setSpanError(span, 'Invalid credentials');
        throw new AuthenticationError('Invalid credentials');
      }

      const token = generateToken({
        userId: user._id.toString(),
        email: user.email,
        role: user.role,
      });

      logger.info('User logged in successfully', {
        'user.id': user._id.toString(),
        'user.email': email,
      });

      authMetrics.loginSuccess.add(1, {
        'user.id': user._id.toString(),
        'user.role': user.role,
      });

      span.setAttributes({
        'user.id': user._id.toString(),
        'user.email': user.email,
        'user.role': user.role,
      });

      span.addEvent('login_success', { 'user.id': user._id.toString() });

      res.json({
        token,
        user: {
          id: user._id,
          email: user.email,
          name: user.name,
          role: user.role,
        },
      });
    });
  } catch (error) {
    next(error);
  }
}

export async function getCurrentUser(
  req: Request,
  res: Response,
  next: NextFunction
): Promise<void> {
  try {
    await withSpan(TRACER_NAME, 'auth.me', async (span) => {
      const user = req.user;

      if (!user) {
        setSpanError(span, 'User not authenticated');
        throw new AuthenticationError();
      }

      span.setAttributes({
        'user.id': user._id.toString(),
        'user.email': user.email,
        'user.role': user.role,
      });

      res.json({
        id: user._id,
        email: user.email,
        name: user.name,
        role: user.role,
      });
    });
  } catch (error) {
    next(error);
  }
}

export async function logout(
  req: Request,
  res: Response,
  next: NextFunction
): Promise<void> {
  try {
    await withSpan(TRACER_NAME, 'auth.logout', async (span) => {
      const user = req.user;

      if (!user) {
        setSpanError(span, 'User not authenticated');
        throw new AuthenticationError();
      }

      logger.info('User logged out', {
        'user.id': user._id.toString(),
        'user.email': user.email,
      });

      authMetrics.logout.add(1, {
        'user.id': user._id.toString(),
        'user.role': user.role,
      });

      span.setAttributes({
        'user.id': user._id.toString(),
        'user.email': user.email,
        'user.role': user.role,
      });

      span.addEvent('logout_success', { 'user.id': user._id.toString() });

      res.json({
        message: 'Logged out successfully',
      });
    });
  } catch (error) {
    next(error);
  }
}
