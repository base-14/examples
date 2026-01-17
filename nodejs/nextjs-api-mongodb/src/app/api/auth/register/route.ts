import { NextRequest, NextResponse } from 'next/server';
import { z } from 'zod';
import { connectDB } from '@/lib/db';
import { User } from '@/models/User';
import { signToken } from '@/lib/auth';
import { ValidationError, ConflictError } from '@/lib/errors';
import { formatZodErrors } from '@/lib/validators';
import { withSpan } from '@/lib/telemetry';
import { logger, logError } from '@/lib/logger';
import { recordAuth } from '@/lib/metrics';
import { checkRateLimit, getRateLimitKey, AUTH_RATE_LIMIT } from '@/lib/ratelimit';
import type { ApiResponse } from '@/types';

const registerSchema = z.object({
  email: z.string().email('Invalid email format'),
  username: z
    .string()
    .min(3, 'Username must be at least 3 characters')
    .max(30, 'Username must be at most 30 characters')
    .regex(
      /^[a-zA-Z0-9_-]+$/,
      'Username can only contain letters, numbers, underscores, and hyphens'
    ),
  password: z
    .string()
    .min(8, 'Password must be at least 8 characters')
    .max(100, 'Password must be at most 100 characters'),
});

interface RegisterResponse {
  user: {
    id: string;
    email: string;
    username: string;
  };
  token: string;
}

export async function POST(
  request: NextRequest
): Promise<NextResponse<ApiResponse<RegisterResponse>>> {
  return withSpan('auth.register', async () => {
    try {
      const ip = request.headers.get('x-forwarded-for') || request.headers.get('x-real-ip');
      const rateLimitKey = getRateLimitKey(ip, 'auth:register');
      const rateLimit = await checkRateLimit(
        rateLimitKey,
        AUTH_RATE_LIMIT.limit,
        AUTH_RATE_LIMIT.windowMs
      );

      if (!rateLimit.success) {
        return NextResponse.json(
          {
            success: false,
            error: 'Too many registration attempts. Please try again later.',
          },
          {
            status: 429,
            headers: {
              'Retry-After': String(rateLimit.reset),
              'X-RateLimit-Remaining': '0',
              'X-RateLimit-Reset': String(rateLimit.reset),
            },
          }
        );
      }

      await connectDB();

      const body = await request.json();
      const validation = registerSchema.safeParse(body);

      if (!validation.success) {
        const errors = formatZodErrors(validation.error);
        throw new ValidationError('Validation failed', errors);
      }

      const { email, username, password } = validation.data;

      const existingUser = await User.findOne({
        $or: [{ email: email.toLowerCase() }, { username }],
      });

      if (existingUser) {
        if (existingUser.email === email.toLowerCase()) {
          throw new ConflictError('Email already registered');
        }
        throw new ConflictError('Username already taken');
      }

      const user = await User.create({ email, username, password });

      const token = signToken({
        userId: user._id.toString(),
        email: user.email,
      });

      recordAuth('register', true);
      logger.info('User registered', { userId: user._id.toString(), username: user.username });
      return NextResponse.json(
        {
          success: true,
          data: {
            user: {
              id: user._id.toString(),
              email: user.email,
              username: user.username,
            },
            token,
          },
        },
        { status: 201 }
      );
    } catch (error) {
      recordAuth('register', false);
      if (error instanceof ValidationError) {
        return NextResponse.json(
          { success: false, error: error.message, details: error.details },
          { status: error.statusCode }
        );
      }
      if (error instanceof ConflictError) {
        return NextResponse.json(
          { success: false, error: error.message },
          { status: error.statusCode }
        );
      }
      logError('Registration failed', error, { operation: 'auth.register' });
      return NextResponse.json(
        { success: false, error: 'Registration failed' },
        { status: 500 }
      );
    }
  });
}
