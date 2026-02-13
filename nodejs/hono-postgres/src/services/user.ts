import bcrypt from 'bcrypt';
import jwt from 'jsonwebtoken';
import { eq } from 'drizzle-orm';
import { trace, SpanStatusCode } from '@opentelemetry/api';
import { db } from '../db/index.js';
import { users, NewUser, User } from '../db/schema.js';
import { config } from '../config/index.js';

const tracer = trace.getTracer('user-service');
const BCRYPT_ROUNDS = 12;

export interface CreateUserInput {
  email: string;
  password: string;
  name: string;
}

export interface UserResponse {
  id: number;
  email: string;
  name: string;
  bio: string | null;
  image: string | null;
  createdAt: Date;
}

function toUserResponse(user: User): UserResponse {
  return {
    id: user.id,
    email: user.email,
    name: user.name,
    bio: user.bio,
    image: user.image,
    createdAt: user.createdAt,
  };
}

export function generateToken(user: UserResponse): string {
  return jwt.sign({ id: user.id, email: user.email }, config.jwt.secret, {
    expiresIn: config.jwt.expiresIn as jwt.SignOptions['expiresIn'],
  });
}

export async function createUser(input: CreateUserInput): Promise<UserResponse> {
  return tracer.startActiveSpan('user.register', async (span) => {
    try {
      span.setAttribute('user.email_domain', input.email.split('@')[1] || 'unknown');

      const existingUser = await db
        .select()
        .from(users)
        .where(eq(users.email, input.email.toLowerCase()))
        .limit(1);

      if (existingUser.length > 0) {
        span.setStatus({ code: SpanStatusCode.ERROR, message: 'Email already exists' });
        throw new Error('Email already exists');
      }

      const passwordHash = await bcrypt.hash(input.password, BCRYPT_ROUNDS);

      const [newUser] = await db
        .insert(users)
        .values({
          email: input.email.toLowerCase(),
          passwordHash,
          name: input.name,
        } satisfies NewUser)
        .returning();

      span.setAttribute('user.id', newUser.id);
      span.setStatus({ code: SpanStatusCode.OK });

      return toUserResponse(newUser);
    } catch (error) {
      span.recordException(error as Error);
      span.setStatus({ code: SpanStatusCode.ERROR, message: (error as Error).message });
      throw error;
    } finally {
      span.end();
    }
  });
}

export async function findByEmail(email: string): Promise<User | null> {
  return tracer.startActiveSpan('user.find_by_email', async (span) => {
    try {
      span.setAttribute('user.email_domain', email.split('@')[1] || 'unknown');

      const [user] = await db
        .select()
        .from(users)
        .where(eq(users.email, email.toLowerCase()))
        .limit(1);

      span.setStatus({ code: SpanStatusCode.OK });
      return user || null;
    } catch (error) {
      span.recordException(error as Error);
      span.setStatus({ code: SpanStatusCode.ERROR });
      throw error;
    } finally {
      span.end();
    }
  });
}

export async function findById(id: number): Promise<UserResponse | null> {
  return tracer.startActiveSpan('user.find_by_id', async (span) => {
    try {
      span.setAttribute('user.id', id);

      const [user] = await db
        .select()
        .from(users)
        .where(eq(users.id, id))
        .limit(1);

      span.setStatus({ code: SpanStatusCode.OK });
      return user ? toUserResponse(user) : null;
    } catch (error) {
      span.recordException(error as Error);
      span.setStatus({ code: SpanStatusCode.ERROR });
      throw error;
    } finally {
      span.end();
    }
  });
}

export async function validateCredentials(
  email: string,
  password: string
): Promise<UserResponse> {
  return tracer.startActiveSpan('user.login', async (span) => {
    try {
      span.setAttribute('user.email_domain', email.split('@')[1] || 'unknown');

      const user = await findByEmail(email);

      if (!user) {
        span.setStatus({ code: SpanStatusCode.ERROR, message: 'Invalid credentials' });
        throw new Error('Invalid credentials');
      }

      const isValid = await bcrypt.compare(password, user.passwordHash);

      if (!isValid) {
        span.setStatus({ code: SpanStatusCode.ERROR, message: 'Invalid credentials' });
        throw new Error('Invalid credentials');
      }

      span.setAttribute('user.id', user.id);
      span.setStatus({ code: SpanStatusCode.OK });

      return toUserResponse(user);
    } catch (error) {
      span.recordException(error as Error);
      span.setStatus({ code: SpanStatusCode.ERROR, message: (error as Error).message });
      throw error;
    } finally {
      span.end();
    }
  });
}

export async function updateUser(
  id: number,
  updates: Partial<Pick<User, 'name' | 'bio' | 'image'>>
): Promise<UserResponse | null> {
  return tracer.startActiveSpan('user.update', async (span) => {
    try {
      span.setAttribute('user.id', id);

      const [updated] = await db
        .update(users)
        .set({
          ...updates,
          updatedAt: new Date(),
        })
        .where(eq(users.id, id))
        .returning();

      span.setStatus({ code: SpanStatusCode.OK });
      return updated ? toUserResponse(updated) : null;
    } catch (error) {
      span.recordException(error as Error);
      span.setStatus({ code: SpanStatusCode.ERROR });
      throw error;
    } finally {
      span.end();
    }
  });
}
