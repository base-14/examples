import bcrypt from 'bcrypt';
import jwt from 'jsonwebtoken';
import { eq } from 'drizzle-orm';
import { trace, SpanStatusCode, metrics } from '@opentelemetry/api';
import { db } from '../db/index.js';
import { users, type User } from '../db/schema.js';
import { logger } from '../logger.js';
import type { JwtPayload } from '../types/index.js';

const tracer = trace.getTracer('auth-service');
const meter = metrics.getMeter('auth-service');

const loginAttemptsCounter = meter.createCounter('auth.login.attempts', {
  description: 'Number of login attempts',
  unit: '1',
});

const registrationCounter = meter.createCounter('auth.registration.total', {
  description: 'Number of user registrations',
  unit: '1',
});

const SALT_ROUNDS = 12;

export class AuthService {
  private jwtSecret: string;
  private jwtExpiresIn: string;

  constructor() {
    this.jwtSecret = process.env.JWT_SECRET || '';
    this.jwtExpiresIn = process.env.JWT_EXPIRES_IN || '7d';
  }

  async register(
    email: string,
    password: string,
    name: string
  ): Promise<{ user: User; token: string }> {
    return tracer.startActiveSpan('user.register', async (span) => {
      try {
        span.setAttribute('user.email_domain', email.split('@')[1] || 'unknown');

        const existingUser = await db.query.users.findFirst({
          where: eq(users.email, email),
        });

        if (existingUser) {
          span.setStatus({ code: SpanStatusCode.ERROR, message: 'Email already exists' });
          throw Object.assign(new Error('Email already registered'), { statusCode: 409 });
        }

        const passwordHash = await bcrypt.hash(password, SALT_ROUNDS);

        const [user] = await db
          .insert(users)
          .values({ email, passwordHash, name })
          .returning();

        if (!user) {
          throw new Error('Failed to create user');
        }

        const token = this.generateToken(user);

        span.setAttribute('user.id', user.id);
        span.setStatus({ code: SpanStatusCode.OK });

        registrationCounter.add(1, { status: 'success' });
        logger.info({ userId: user.id }, 'User registered successfully');

        return { user, token };
      } catch (error) {
        span.recordException(error as Error);
        span.setStatus({ code: SpanStatusCode.ERROR });
        registrationCounter.add(1, { status: 'failure' });
        throw error;
      } finally {
        span.end();
      }
    });
  }

  async login(email: string, password: string): Promise<{ user: User; token: string }> {
    return tracer.startActiveSpan('user.login', async (span) => {
      try {
        span.setAttribute('user.email_domain', email.split('@')[1] || 'unknown');
        loginAttemptsCounter.add(1);

        const user = await db.query.users.findFirst({
          where: eq(users.email, email),
        });

        if (!user) {
          span.setStatus({ code: SpanStatusCode.ERROR, message: 'Invalid credentials' });
          throw Object.assign(new Error('Invalid credentials'), { statusCode: 401 });
        }

        const isValidPassword = await bcrypt.compare(password, user.passwordHash);

        if (!isValidPassword) {
          span.setStatus({ code: SpanStatusCode.ERROR, message: 'Invalid credentials' });
          throw Object.assign(new Error('Invalid credentials'), { statusCode: 401 });
        }

        const token = this.generateToken(user);

        span.setAttribute('user.id', user.id);
        span.setStatus({ code: SpanStatusCode.OK });

        logger.info({ userId: user.id }, 'User logged in successfully');

        return { user, token };
      } catch (error) {
        span.recordException(error as Error);
        span.setStatus({ code: SpanStatusCode.ERROR });
        throw error;
      } finally {
        span.end();
      }
    });
  }

  async getUserById(id: number): Promise<User | null> {
    const user = await db.query.users.findFirst({
      where: eq(users.id, id),
    });
    return user || null;
  }

  verifyToken(token: string): JwtPayload {
    return jwt.verify(token, this.jwtSecret) as JwtPayload;
  }

  private generateToken(user: User): string {
    const payload: JwtPayload = {
      userId: user.id,
      email: user.email,
    };
    // Cast expiresIn to the expected type (string like "7d" or number in seconds)
    return jwt.sign(payload, this.jwtSecret, {
      expiresIn: this.jwtExpiresIn as `${number}${'s' | 'm' | 'h' | 'd' | 'w' | 'y'}`
    });
  }
}

export const authService = new AuthService();
